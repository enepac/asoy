"""Parse, assemble, export, and the end-to-end conversion of a text-only EPUB.

Covers ARCHITECTURE sections 4.4, 4.8 and 4.9, invariant 3 (verbatim author text), and the
parse-to-emit chapter-count assertion named in CLAUDE.md section 4.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from asoy.assemble import count_chapter_headings, render
from asoy.export import OutputVerificationError, write
from asoy.orchestrator import ChapterCountMismatch, ConversionRefused, convert
from asoy.parser import Block, BlockKind, Chapter, ParsedDocument, parse
from asoy.router import CalibreConversionNotImplemented, Route
from tests.epub_fixtures import (
    CHAPTER_ONE,
    CHAPTER_TWO,
    CONTENT_ENCRYPTION_ALGORITHM,
    FRONT_MATTER_THEN_CHAPTER,
    ODT_TWO_CHAPTERS,
    add_encryption_xml,
    build_epub,
    build_mobi,
    build_odt,
)

VERBATIM_SENTENCE = "It was a bright cold day in April, and the clocks were striking thirteen."
MISSPELLED_SENTENCE = (
    "This sentance keeps its own misspelling, and its _underscores_ and *asterisks*."
)


@pytest.fixture(scope="module")
def two_chapter_epub(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("books")
    return build_epub(
        directory / "two-chapters.epub", [("ch1", CHAPTER_ONE), ("ch2", CHAPTER_TWO)]
    )


@pytest.fixture(scope="module")
def parsed_two_chapters(two_chapter_epub: Path) -> ParsedDocument:
    return parse(two_chapter_epub)


# --- Parser ------------------------------------------------------------------------------------


def test_chapters_are_segmented_on_top_level_headings(parsed_two_chapters: ParsedDocument) -> None:
    assert parsed_two_chapters.chapter_count == 2
    assert [chapter.title for chapter in parsed_two_chapters.chapters] == [
        "The First Chapter",
        "The Second Chapter",
    ]


def test_subsection_stays_inside_its_chapter(parsed_two_chapters: ParsedDocument) -> None:
    first = parsed_two_chapters.chapters[0]
    headings = [b.text for b in first.blocks if b.kind is BlockKind.HEADING]
    assert headings == ["A Subsection"]


def test_author_text_is_verbatim(parsed_two_chapters: ParsedDocument) -> None:
    """Invariant 3. The misspelling and the metacharacters survive untouched."""
    paragraphs = [
        b.text
        for chapter in parsed_two_chapters.chapters
        for b in chapter.blocks
        if b.kind is BlockKind.PARAGRAPH
    ]
    assert VERBATIM_SENTENCE in paragraphs
    assert MISSPELLED_SENTENCE in paragraphs, "author text must not be spell-fixed or escaped"


def test_front_matter_before_the_first_heading_is_kept(tmp_path: Path) -> None:
    """Content before the first chapter heading is still the author's, so it cannot be dropped."""
    book = build_epub(tmp_path / "front.epub", [("ch1", FRONT_MATTER_THEN_CHAPTER)])
    document = parse(book)

    assert document.chapters[0].is_front_matter
    front_text = [b.text for b in document.chapters[0].blocks]
    assert "Front matter before any heading. It must not be dropped." in front_text
    assert document.titled_chapter_count == 1


def test_parse_reports_a_missing_file_rather_than_returning_empty(tmp_path: Path) -> None:
    from asoy.parser import ParseError

    with pytest.raises(ParseError):
        parse(tmp_path / "nope.epub")


# --- Assembler ---------------------------------------------------------------------------------


def _document(*chapters: Chapter) -> ParsedDocument:
    return ParsedDocument(source=Path("x.epub"), chapters=tuple(chapters), undescribed=())


def test_markdown_uses_one_hash_per_chapter() -> None:
    document = _document(
        Chapter(title="One", blocks=(Block(BlockKind.PARAGRAPH, "Body one."),)),
        Chapter(title="Two", blocks=(Block(BlockKind.PARAGRAPH, "Body two."),)),
    )
    rendered = render(document)
    assert rendered.markdown == "# One\n\nBody one.\n\n# Two\n\nBody two.\n"
    assert count_chapter_headings(rendered.markdown) == 2


def test_subsection_headings_are_nested_below_the_chapter() -> None:
    document = _document(
        Chapter(title="One", blocks=(Block(BlockKind.HEADING, "Sub", level=2),))
    )
    assert render(document).markdown == "# One\n\n## Sub\n"


def test_flattened_text_carries_no_structural_markers() -> None:
    document = _document(
        Chapter(
            title="One",
            blocks=(
                Block(BlockKind.HEADING, "Sub", level=2),
                Block(BlockKind.PARAGRAPH, "Body."),
            ),
        )
    )
    rendered = render(document)
    assert "#" not in rendered.plain_text
    assert rendered.plain_text == "One\n\nSub\n\nBody.\n"


def test_assembler_adds_nothing_to_author_text() -> None:
    """Only the heading hashes and the blank lines are ours."""
    awkward = "A line with _underscores_, *asterisks*, a [bracket] and a trailing backslash \\"
    document = _document(Chapter(title=None, blocks=(Block(BlockKind.PARAGRAPH, awkward),)))
    rendered = render(document)
    assert rendered.markdown == f"{awkward}\n"
    assert rendered.plain_text == f"{awkward}\n"


def test_heading_counter_does_not_count_subsections() -> None:
    assert count_chapter_headings("# A\n## B\n### C\n# D\n") == 2


# --- Exporter and the parse-to-emit assertion --------------------------------------------------


def test_export_writes_both_artifacts(tmp_path: Path) -> None:
    document = _document(Chapter(title="One", blocks=(Block(BlockKind.PARAGRAPH, "Body."),)))
    artifacts = write(render(document), tmp_path, "book")

    assert artifacts.markdown_path.read_text(encoding="utf-8") == "# One\n\nBody.\n"
    assert artifacts.text_path.read_text(encoding="utf-8") == "One\n\nBody.\n"


def test_export_detects_a_truncated_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Silent truncation looks like success. It must not survive to a zero exit code."""
    document = _document(
        Chapter(title="One", blocks=(Block(BlockKind.PARAGRAPH, "Body."),)),
        Chapter(title="Two", blocks=(Block(BlockKind.PARAGRAPH, "More."),)),
    )
    real_write_text = Path.write_text

    def truncating_write_text(self: Path, data: str, *args, **kwargs):
        return real_write_text(self, data[: len(data) // 2], *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", truncating_write_text)
    with pytest.raises(OutputVerificationError):
        write(render(document), tmp_path, "book")


def test_chapter_count_mismatch_aborts_before_writing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The assertion CLAUDE.md section 4 requires between parse and emit."""
    from asoy import orchestrator

    document = _document(
        Chapter(title="One", blocks=()),
        Chapter(title="Two", blocks=()),
    )
    with pytest.raises(ChapterCountMismatch):
        orchestrator._assert_chapter_counts(document, "# One\n", rendered_count=2)


def test_chapter_count_mismatch_on_rendered_count() -> None:
    from asoy import orchestrator

    document = _document(Chapter(title="One", blocks=()))
    with pytest.raises(ChapterCountMismatch):
        orchestrator._assert_chapter_counts(document, "# One\n", rendered_count=5)


# --- End to end ---------------------------------------------------------------------------------


def test_text_only_epub_converts_end_to_end(two_chapter_epub: Path, tmp_path: Path) -> None:
    result = convert(two_chapter_epub, tmp_path)

    markdown = result.artifacts.markdown_path.read_text(encoding="utf-8")
    assert markdown.startswith("# The First Chapter")
    assert "# The Second Chapter" in markdown
    assert "## A Subsection" in markdown
    assert VERBATIM_SENTENCE in markdown
    assert MISSPELLED_SENTENCE in markdown
    assert count_chapter_headings(markdown) == 2
    assert result.artifacts.chapter_count == 2

    flattened = result.artifacts.text_path.read_text(encoding="utf-8")
    assert VERBATIM_SENTENCE in flattened
    assert not flattened.startswith("#")


def test_text_only_odt_converts_without_calibre(tmp_path: Path) -> None:
    """ADR-023: ODT is parsed by Docling directly, so no external program is involved."""
    book = build_odt(tmp_path / "book.odt", ODT_TWO_CHAPTERS)
    result = convert(book, tmp_path / "out")

    assert result.decision.route is Route.DIRECT

    markdown = result.artifacts.markdown_path.read_text(encoding="utf-8")
    assert markdown.startswith("# The First Chapter")
    assert "# The Second Chapter" in markdown
    assert VERBATIM_SENTENCE in markdown
    assert count_chapter_headings(markdown) == 2


def test_no_description_delimiter_is_invented(two_chapter_epub: Path, tmp_path: Path) -> None:
    """ADR-006: the delimiter is an undefined public interface. Nothing may pre-empt its shape."""
    result = convert(two_chapter_epub, tmp_path)
    markdown = result.artifacts.markdown_path.read_text(encoding="utf-8")
    for shape in ("[[", "]]", "<description", "{{", "::description"):
        assert shape not in markdown


def test_drm_protected_book_is_refused_end_to_end(tmp_path: Path) -> None:
    book = build_epub(tmp_path / "drm.epub", [("ch1", CHAPTER_ONE)])
    add_encryption_xml(book, CONTENT_ENCRYPTION_ALGORITHM)

    with pytest.raises(ConversionRefused) as excinfo:
        convert(book, tmp_path / "out")

    assert "DRM" in str(excinfo.value)
    assert not (tmp_path / "out").exists(), "nothing may be written for a refused book"


def test_calibre_path_fails_loudly_rather_than_silently(tmp_path: Path) -> None:
    """Invariant 5. Not implemented is reported, never approximated."""
    book = build_mobi(tmp_path / "book.azw3", encryption=0)
    with pytest.raises(CalibreConversionNotImplemented):
        convert(book, tmp_path / "out")


def test_document_with_images_is_refused_rather_than_silently_stripped(tmp_path: Path) -> None:
    """CLAUDE.md section 9: dropping a block gives cleaner output and a dishonest result."""
    from asoy import orchestrator
    from asoy.parser import UndescribedBlock

    document = ParsedDocument(
        source=tmp_path / "book.epub",
        chapters=(Chapter(title="One", blocks=(Block(BlockKind.PARAGRAPH, "Body."),)),),
        undescribed=(UndescribedBlock(kind="picture", locator="picture[0]"),),
    )
    monkey = tmp_path / "book.epub"
    build_epub(monkey, [("ch1", CHAPTER_ONE)])

    orchestrator_parse = orchestrator.parse
    try:
        orchestrator.parse = lambda _path: document  # type: ignore[assignment]
        with pytest.raises(ConversionRefused) as excinfo:
            convert(monkey, tmp_path / "out")
    finally:
        orchestrator.parse = orchestrator_parse  # type: ignore[assignment]

    assert "picture" in str(excinfo.value)
    assert not (tmp_path / "out").exists()
