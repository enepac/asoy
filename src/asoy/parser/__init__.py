"""Document Parser: Docling wrapper for layout and reading order (ARCHITECTURE section 4.4).

Produces the structured representation the assembler emits from. Headings become the basis for
chapter segmentation (section 4.4), and every text-bearing item is carried through.

**Author text is verbatim (invariant 3).** This module reads each item's raw text rather than
Docling's own `export_to_markdown()`, because that export escapes some Markdown metacharacters
and not others: a passage containing `_word_` comes back as `\\_word\\_` while `*word*` is left
alone. Escaping is a rendering decision, and an inconsistent one silently changes the text. The
raw item text is what the author wrote, so that is what is carried.

**Nothing is dropped.** A text item whose label this module does not specifically model is still
emitted as a paragraph rather than skipped, and non-text blocks are counted and reported rather
than quietly omitted (CLAUDE.md section 9).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

MAX_HEADING_LEVEL = 6

# Docling labels that carry a chapter-level heading. An EPUB's <h1> arrives as "title".
_CHAPTER_LABELS = frozenset({"title"})
_SECTION_LABELS = frozenset({"section_header"})

# Labels that carry no author prose and would add noise to a narration.
_SKIPPABLE_LABELS = frozenset({"page_header", "page_footer"})


class BlockKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"


@dataclass(frozen=True)
class Block:
    """One emitted unit of author text."""

    kind: BlockKind
    text: str
    level: int = 0


@dataclass(frozen=True)
class Chapter:
    """A chapter heading and everything under it. `title` is None for pre-heading front matter."""

    title: str | None
    blocks: tuple[Block, ...]

    @property
    def is_front_matter(self) -> bool:
        return self.title is None


@dataclass(frozen=True)
class UndescribedBlock:
    """A non-text block that would need a generated description before it can be emitted."""

    kind: str
    locator: str


@dataclass(frozen=True)
class ParsedDocument:
    """The parsed book."""

    source: Path
    chapters: tuple[Chapter, ...]
    undescribed: tuple[UndescribedBlock, ...]

    @property
    def chapter_count(self) -> int:
        return len(self.chapters)

    @property
    def titled_chapter_count(self) -> int:
        return sum(1 for chapter in self.chapters if not chapter.is_front_matter)

    @property
    def block_count(self) -> int:
        return sum(len(chapter.blocks) for chapter in self.chapters)


class ParseError(RuntimeError):
    """Docling could not parse the document. Raised rather than returning an empty result."""


def _label_of(item: object) -> str:
    label = getattr(item, "label", "")
    return str(getattr(label, "value", label))


def _heading_level(item: object) -> int:
    raw = getattr(item, "level", None)
    try:
        level = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1
    return max(1, level)


def _to_blocks_and_chapters(items: list[tuple[str, str, int]]) -> tuple[Chapter, ...]:
    """Segment a flat, ordered list of (label, text, level) into chapters."""
    has_chapter_label = any(label in _CHAPTER_LABELS for label, _, _ in items)

    # Fall back to the shallowest section heading when a book has no top-level title items, so a
    # book whose chapters are marked up as <h2> still segments instead of collapsing into one.
    fallback_level = 0
    if not has_chapter_label:
        section_levels = [level for label, _, level in items if label in _SECTION_LABELS]
        fallback_level = min(section_levels) if section_levels else 0

    def starts_chapter(label: str, level: int) -> bool:
        if has_chapter_label:
            return label in _CHAPTER_LABELS
        return bool(fallback_level) and label in _SECTION_LABELS and level == fallback_level

    chapters: list[Chapter] = []
    title: str | None = None
    blocks: list[Block] = []

    def flush() -> None:
        if title is not None or blocks:
            chapters.append(Chapter(title=title, blocks=tuple(blocks)))

    for label, text, level in items:
        if starts_chapter(label, level):
            flush()
            title = text
            blocks = []
            continue

        if label in _SECTION_LABELS:
            depth = min(level + 1, MAX_HEADING_LEVEL)
            blocks.append(Block(kind=BlockKind.HEADING, text=text, level=depth))
            continue

        blocks.append(Block(kind=BlockKind.PARAGRAPH, text=text))

    flush()
    return tuple(chapters)


def _release(result: object) -> None:
    """Close Docling's handle on the file it just read.

    Docling's SimplePipeline — which serves EPUB, DOCX, ODT, and the other declarative formats —
    inherits a no-op unload, so the backend's open ZipFile survives the call and the source stays
    open until garbage collection gets to it. On Windows an open handle prevents deletion, which
    breaks the removal of the job's temp directory (ARCHITECTURE section 7) on every format that
    goes through Calibre first, at the very end of a job that otherwise succeeded.

    This reaches into a private attribute on purpose (ADR-024). There is no public release call,
    and the alternative is holding a book file open for the life of the process. It is guarded so
    that a change in Docling's internals degrades to the old behaviour rather than failing a good
    parse: a leaked handle is a cleanup problem, and raising here would turn it into a lost
    conversion. Because the guard hides a break, the real guard is the test —
    `test_parse_does_not_hold_the_file_open`. Treat a Docling upgrade as touching this function.
    """
    backend = getattr(getattr(result, "input", None), "_backend", None)
    unload = getattr(backend, "unload", None)
    if callable(unload):
        try:
            unload()
        except Exception:  # noqa: BLE001 - see above; there is nothing here to report to a user
            pass


def parse(path: Path) -> ParsedDocument:
    """Parse a document into chapters. Raises ParseError if Docling cannot read it.

    The file is not held open after this returns. See `_release`.
    """
    from docling.document_converter import DocumentConverter

    try:
        result = DocumentConverter().convert(path)
    except Exception as exc:
        raise ParseError(f"Docling failed to convert {path}: {type(exc).__name__}: {exc}") from exc

    try:
        return _extract(path, result)
    finally:
        _release(result)


def _extract(path: Path, result: object) -> ParsedDocument:
    """Turn one Docling conversion result into a ParsedDocument."""
    status = str(getattr(result.status, "value", result.status)).lower()
    if status not in {"success", "partial_success"}:
        errors = "; ".join(str(e) for e in getattr(result, "errors", []) or []) or "no detail"
        raise ParseError(f"Docling reported status {status} for {path} ({errors}).")

    document = result.document
    items: list[tuple[str, str, int]] = []
    for item, _depth in document.iterate_items(with_groups=False):
        label = _label_of(item)
        if label in _SKIPPABLE_LABELS:
            continue
        text = getattr(item, "text", None)
        if text is None or not str(text).strip():
            continue
        items.append((label, str(text), _heading_level(item)))

    undescribed = tuple(
        [
            UndescribedBlock(kind="picture", locator=f"picture[{index}]")
            for index in range(len(getattr(document, "pictures", []) or []))
        ]
        + [
            UndescribedBlock(kind="table", locator=f"table[{index}]")
            for index in range(len(getattr(document, "tables", []) or []))
        ]
    )

    return ParsedDocument(
        source=path,
        chapters=_to_blocks_and_chapters(items),
        undescribed=undescribed,
    )
