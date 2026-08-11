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

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from asoy.fences import MAX_HEADING_LEVEL, DescriptionType

# Docling labels that carry a chapter-level heading. An EPUB's <h1> arrives as "title".
_CHAPTER_LABELS = frozenset({"title"})
_SECTION_LABELS = frozenset({"section_header"})

# Labels that carry no author prose and would add noise to a narration.
_SKIPPABLE_LABELS = frozenset({"page_header", "page_footer"})

# Non-text labels, which become descriptions rather than being dropped (invariant 7).
_PICTURE_LABEL = "picture"
_TABLE_LABEL = "table"


class BlockKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    NON_TEXT = "non_text"


@dataclass(frozen=True)
class NonText:
    """A block carrying no author prose: a picture, a table, a chart.

    `type` is what the block classifier would assign. It does not exist yet, so a picture arrives
    as `unknown` rather than being guessed at — the closed set has a member for not knowing, and
    using it is more honest than asserting `illustration` on no evidence.

    `table` carries the cells when Docling extracted them cleanly, so the assembler can render the
    structure rather than sending a picture of a table to a vision model (section 4.6).
    """

    type: DescriptionType
    locator: str
    table: tuple[tuple[str, ...], ...] | None = None
    # Why a table's cells were rejected, when they were. Empty for pictures and for tables whose
    # structure came through. Surfaced so a gated table names its own cause (ADR-031).
    detail: str = ""


@dataclass(frozen=True)
class Block:
    """One emitted unit: author text, or a non-text block awaiting a description."""

    kind: BlockKind
    text: str = ""
    level: int = 0
    non_text: NonText | None = None


@dataclass(frozen=True)
class Chapter:
    """A chapter heading and everything under it. `title` is None for pre-heading front matter."""

    title: str | None
    blocks: tuple[Block, ...]

    @property
    def is_front_matter(self) -> bool:
        return self.title is None


@dataclass(frozen=True)
class ParsedDocument:
    """The parsed book."""

    source: Path
    chapters: tuple[Chapter, ...]

    @property
    def chapter_count(self) -> int:
        return len(self.chapters)

    @property
    def titled_chapter_count(self) -> int:
        return sum(1 for chapter in self.chapters if not chapter.is_front_matter)

    @property
    def block_count(self) -> int:
        return sum(len(chapter.blocks) for chapter in self.chapters)

    @property
    def gated_tables(self) -> tuple[NonText, ...]:
        """Tables whose structure was rejected and which fall through to a description.

        Reported on every conversion (ADR-031). The gate has no reference set behind it, so the
        count is how anyone would notice it firing too often or not at all.
        """
        return tuple(
            block
            for block in self.non_text_blocks
            if block.type is DescriptionType.TABLE and block.table is None
        )

    @property
    def non_text_blocks(self) -> tuple[NonText, ...]:
        """Every non-text block, in reading order. What the review UI will list."""
        return tuple(
            block.non_text
            for chapter in self.chapters
            for block in chapter.blocks
            if block.non_text is not None
        )


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


@dataclass(frozen=True)
class _Item:
    """One item from Docling, still in document order and not yet segmented into chapters."""

    label: str
    text: str = ""
    level: int = 1
    non_text: NonText | None = None


def _to_blocks_and_chapters(items: list[_Item]) -> tuple[Chapter, ...]:
    """Segment a flat, ordered list of items into chapters."""
    has_chapter_label = any(item.label in _CHAPTER_LABELS for item in items)

    # Fall back to the shallowest section heading when a book has no top-level title items, so a
    # book whose chapters are marked up as <h2> still segments instead of collapsing into one.
    fallback_level = 0
    if not has_chapter_label:
        section_levels = [item.level for item in items if item.label in _SECTION_LABELS]
        fallback_level = min(section_levels) if section_levels else 0

    def starts_chapter(item: _Item) -> bool:
        if has_chapter_label:
            return item.label in _CHAPTER_LABELS
        return (
            bool(fallback_level)
            and item.label in _SECTION_LABELS
            and item.level == fallback_level
        )

    chapters: list[Chapter] = []
    title: str | None = None
    blocks: list[Block] = []

    def flush() -> None:
        if title is not None or blocks:
            chapters.append(Chapter(title=title, blocks=tuple(blocks)))

    for item in items:
        if item.non_text is not None:
            blocks.append(Block(kind=BlockKind.NON_TEXT, non_text=item.non_text))
            continue

        if starts_chapter(item):
            flush()
            title = item.text
            blocks = []
            continue

        if item.label in _SECTION_LABELS:
            depth = min(item.level + 1, MAX_HEADING_LEVEL)
            blocks.append(Block(kind=BlockKind.HEADING, text=item.text, level=depth))
            continue

        blocks.append(Block(kind=BlockKind.PARAGRAPH, text=item.text))

    flush()
    return tuple(chapters)


# Formats whose pipeline runs OCR, and therefore needs the weights present. The declarative
# formats — EPUB, DOCX, ODT, HTML — never touch it, which is exactly why every OCR defect in
# INC-001 through INC-003 went unnoticed while four books converted successfully.
_OCR_SUFFIXES = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"})


def _converter_for(path: Path):
    """Build the converter for this input, configuring OCR only when the format needs it.

    Two things are set for the OCR formats, both from ADR-029. Every model path is passed
    explicitly, so RapidOCR has nothing to resolve and cannot fetch during a conversion. And
    `torch.compile` is disabled, because TorchInductor needs a C++ compiler that is absent on
    essentially every user machine.
    """
    from docling.document_converter import DocumentConverter

    if path.suffix.lower() not in _OCR_SUFFIXES:
        return DocumentConverter()

    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import ImageFormatOption, PdfFormatOption

    from asoy.ocr import disable_torch_compile, ocr_options

    disable_torch_compile()

    pipeline = PdfPipelineOptions()
    pipeline.ocr_options = ocr_options()

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline),
            InputFormat.IMAGE: ImageFormatOption(pipeline_options=pipeline),
        }
    )


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
    converter = _converter_for(path)

    try:
        result = converter.convert(path)
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
    items: list[_Item] = []
    pictures = 0
    tables = 0

    for item, _depth in document.iterate_items(with_groups=False):
        label = _label_of(item)
        if label in _SKIPPABLE_LABELS:
            continue

        # Non-text blocks are carried in reading order rather than counted separately, because
        # their position is the whole point: a description read out at the wrong moment is worse
        # than the silence it replaced (section 4.7).
        if label == _PICTURE_LABEL:
            items.append(
                _Item(
                    label=label,
                    non_text=NonText(
                        type=DescriptionType.UNKNOWN, locator=f"picture[{pictures}]"
                    ),
                )
            )
            pictures += 1
            continue

        if label == _TABLE_LABEL:
            items.append(
                _Item(
                    label=label,
                    non_text=_table_block(item, tables),
                )
            )
            tables += 1
            continue

        text = getattr(item, "text", None)
        if text is None or not str(text).strip():
            continue
        items.append(_Item(label=label, text=str(text), level=_heading_level(item)))

    return ParsedDocument(source=path, chapters=_to_blocks_and_chapters(items))


# A cell holding this many numeric tokens is a collapsed column, not a value (ADR-031).
# Four is deliberately generous: a cell legitimately reading "1,234.5" is one token, and a date
# range or a footnote marker beside a figure is two or three.
_COLLAPSED_CELL_TOKENS = 4

_NUMERIC_TOKEN = re.compile(r"^[$(]?[\d,.]*\d[\d,.]*[)%]?\.?$")


def _table_problem(rows: tuple[tuple[str, ...], ...]) -> str:
    """Why this extracted structure cannot be narrated, or "" when it can (ADR-031).

    Checkable facts about the extraction, not a tuned score. Each one names output a listener
    could not use, and the two differ in kind:

    * A collapsed cell produces output that is **wrong** — a cell holding a whole column of years
      beside a cell holding a whole column of values pairs every label with the wrong number.
    * Unnamed columns produce output that is **useless** — the values are correctly paired and
      nothing says what they are, so a listener hears figures with no referent.

    The blank top-left corner is not counted. Nearly every table has one, and gating on it would
    send almost every table to the model.
    """
    if not rows:
        return "no rows"

    header, *body = rows
    if not body:
        return "the extraction found headings but no rows, so there is nothing to read out"

    if len(header) > 1 and any(not cell for cell in header[1:]):
        unnamed = sum(1 for cell in header[1:] if not cell)
        return f"{unnamed} of {len(header)} columns have no heading"

    # Every row, the heading included. A collapsed column lands in the heading row as readily as
    # in a body row, and a heading holding a column of figures is the same defect one line up.
    for index, row in enumerate(rows):
        for cell in row:
            # Counted, not required of every token: OCR leaves stray words inside a collapsed
            # column — a unit heading, a month abbreviation — and demanding that all of them be
            # numeric let the worst tables through on one non-numeric word.
            figures = sum(1 for token in cell.split() if _NUMERIC_TOKEN.match(token))
            if figures >= _COLLAPSED_CELL_TOKENS:
                where = "the heading row" if index == 0 else f"row {index}"
                return (
                    f"{where} has a cell holding {figures} figures in one place, so the "
                    "extraction collapsed a column rather than splitting it"
                )
    return ""


def _table_cells(item: object) -> tuple[tuple[tuple[str, ...], ...] | None, str]:
    """The table's cells as rows of strings, plus why they were rejected if they were.

    "Cleanly" is the test ARCHITECTURE 4.6 needs: a table whose structure came through is
    rendered from that structure, and one that did not becomes a description like any other
    picture. A half-extracted table rendered as if it were whole is the worst of the three, and on
    scanned input it is the common case rather than the rare one (ADR-031, INC-004).
    """
    grid = getattr(getattr(item, "data", None), "grid", None)
    if not grid:
        return None, "Docling extracted no cell structure"

    rows = tuple(
        tuple(str(getattr(cell, "text", "") or "").strip() for cell in row) for row in grid
    )
    if not any(any(cell for cell in row) for row in rows):
        return None, "every extracted cell is empty"

    problem = _table_problem(rows)
    if problem:
        return None, problem
    return rows, ""


def _table_block(item: object, index: int) -> NonText:
    """One table as a non-text block, gated on whether its structure can be narrated."""
    rows, problem = _table_cells(item)
    return NonText(
        type=DescriptionType.TABLE, locator=f"table[{index}]", table=rows, detail=problem
    )
