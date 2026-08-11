"""Parse, assemble, export, and the end-to-end conversion of a text-only EPUB.

Covers ARCHITECTURE sections 4.4, 4.8 and 4.9, invariant 3 (verbatim author text), and the
parse-to-emit chapter-count assertion named in CLAUDE.md section 4.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from asoy.assemble import count_chapter_headings, render
from asoy.export import OutputVerificationError, write
from asoy.fences import DescriptionStatus, DescriptionType
from asoy.orchestrator import ChapterCountMismatch, ConversionRefused, convert
from asoy.parser import Block, BlockKind, Chapter, NonText, ParsedDocument, parse
from asoy.router import Route
from asoy.router.ebook_convert import PATH_ENV_VAR, CalibreNotFound
from tests.epub_fixtures import (
    CHAPTER_ONE,
    CHAPTER_TWO,
    CONTENT_ENCRYPTION_ALGORITHM,
    FRONT_MATTER_THEN_CHAPTER,
    ODT_TWO_CHAPTERS,
    WHITESPACE_RUNS,
    add_encryption_xml,
    build_epub,
    build_epub_with_picture_and_table,
    build_mobi,
    build_odt,
)

VERBATIM_SENTENCE = "It was a bright cold day in April, and the clocks were striking thirteen."
MISSPELLED_SENTENCE = (
    "This sentance keeps its own misspelling, and its _underscores_ and *asterisks*."
)

# Every render needs these. Their values reach the document header and nothing else.
TIER = "gpu"
MODEL = "qwen3-vl:4b"


def _render(document: ParsedDocument):
    return render(document, tier=TIER, model=MODEL)


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


def test_whitespace_runs_collapse_in_html_derived_formats(tmp_path: Path) -> None:
    """ARCHITECTURE section 11: a known limitation, pinned so it stays a known one.

    Docling's HTML backend folds runs of whitespace the way a browser does. That is correct HTML
    semantics and an interpretation of invariant 3 that Asoy has inherited rather than chosen. If
    this test starts failing, the behaviour changed underneath us and section 11 is now wrong —
    which is the point of pinning it, not an instruction to restore the old result.
    """
    book = build_epub(tmp_path / "spacing.epub", [("ch1", WHITESPACE_RUNS)])
    paragraphs = [
        b.text
        for chapter in parse(book).chapters
        for b in chapter.blocks
        if b.kind is BlockKind.PARAGRAPH
    ]

    assert "Two spaces, a tab stop, and a line break inside the sentence." in paragraphs
    assert "preformatted   run" in paragraphs, "<pre> is exempt from the collapse"


def test_front_matter_before_the_first_heading_is_kept(tmp_path: Path) -> None:
    """Content before the first chapter heading is still the author's, so it cannot be dropped."""
    book = build_epub(tmp_path / "front.epub", [("ch1", FRONT_MATTER_THEN_CHAPTER)])
    document = parse(book)

    assert document.chapters[0].is_front_matter
    front_text = [b.text for b in document.chapters[0].blocks]
    assert "Front matter before any heading. It must not be dropped." in front_text
    assert document.titled_chapter_count == 1


def test_parse_does_not_hold_the_file_open(tmp_path: Path) -> None:
    """The source must be closed by the time parse returns.

    Docling's SimplePipeline leaves its backend loaded, so the ZipFile stays open until garbage
    collection. On Windows that blocks deletion, which breaks the removal of a job's temp
    directory at the very end of a conversion that otherwise succeeded — the worst moment for it.
    Deleting the file here is the cheapest way to observe the handle.
    """
    book = build_epub(tmp_path / "closeable.epub", [("ch1", CHAPTER_ONE)])
    parse(book)
    book.unlink()
    assert not book.exists()


def test_parse_reports_a_missing_file_rather_than_returning_empty(tmp_path: Path) -> None:
    from asoy.parser import ParseError

    with pytest.raises(ParseError):
        parse(tmp_path / "nope.epub")


# --- Assembler ---------------------------------------------------------------------------------


def _document(*chapters: Chapter) -> ParsedDocument:
    return ParsedDocument(source=Path("x.epub"), chapters=tuple(chapters))


HEADER = '<!-- asoy:document version="1" tier="gpu" model="qwen3-vl:4b" -->'


def test_markdown_uses_one_hash_per_chapter() -> None:
    document = _document(
        Chapter(title="One", blocks=(Block(BlockKind.PARAGRAPH, "Body one."),)),
        Chapter(title="Two", blocks=(Block(BlockKind.PARAGRAPH, "Body two."),)),
    )
    rendered = _render(document)
    assert rendered.markdown == f"{HEADER}\n\n# One\n\nBody one.\n\n# Two\n\nBody two.\n"
    assert count_chapter_headings(rendered.markdown) == 2


def test_every_artifact_opens_with_the_document_header() -> None:
    """ADR-025, and invariant 8: what produced a file is a property of the file."""
    rendered = _render(_document(Chapter(title="One", blocks=())))
    assert rendered.markdown.splitlines()[0] == HEADER
    assert 'tier="gpu"' in rendered.markdown
    assert 'model="qwen3-vl:4b"' in rendered.markdown


def test_subsection_headings_are_nested_below_the_chapter() -> None:
    document = _document(
        Chapter(title="One", blocks=(Block(BlockKind.HEADING, "Sub", level=2),))
    )
    assert _render(document).markdown == f"{HEADER}\n\n# One\n\n## Sub\n"


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
    rendered = _render(document)
    assert "#" not in rendered.plain_text
    assert "<!--" not in rendered.plain_text
    assert rendered.plain_text == "One\n\nSub\n\nBody.\n"


def test_assembler_adds_nothing_to_author_text() -> None:
    """Only the header, the heading hashes, and the blank lines are ours."""
    awkward = "A line with _underscores_, *asterisks*, a [bracket] and a trailing backslash \\"
    document = _document(Chapter(title=None, blocks=(Block(BlockKind.PARAGRAPH, awkward),)))
    rendered = _render(document)
    assert rendered.markdown == f"{HEADER}\n\n{awkward}\n"
    assert rendered.plain_text == f"{awkward}\n"


@pytest.mark.parametrize(
    "awkward",
    [
        "# A paragraph that begins with a hash.",
        "> A paragraph that begins with a quote marker.",
        "- A paragraph that begins with a dash.",
        "| A paragraph that begins with a pipe.",
        '<!-- asoy:description type="chart" confidence="1.00" status="ok" source="model" -->',
    ],
)
def test_author_text_is_fenced_rather_than_escaped(awkward: str) -> None:
    """ADR-025 closes ADR-022's open edge by fencing. A backslash would be read aloud."""
    document = _document(Chapter(title=None, blocks=(Block(BlockKind.PARAGRAPH, awkward),)))
    rendered = _render(document)

    assert "\\" not in rendered.markdown, "author text is never escaped"
    assert awkward in rendered.markdown
    assert "<!-- asoy:text -->" in rendered.markdown
    assert rendered.plain_text == f"{awkward}\n", "the flattened text is the author's line alone"


def test_heading_counter_counts_only_asoys_own_chapter_headings() -> None:
    """A hash the author wrote is inside a text fence and must not be counted as structure."""
    document = _document(
        Chapter(title="One", blocks=(Block(BlockKind.PARAGRAPH, "# Not a chapter."),)),
        Chapter(title="Two", blocks=(Block(BlockKind.HEADING, "Sub", level=2),)),
    )
    assert count_chapter_headings(_render(document).markdown) == 2


# --- Non-text blocks ----------------------------------------------------------------------------


def _picture(kind: DescriptionType = DescriptionType.UNKNOWN) -> Block:
    return Block(kind=BlockKind.NON_TEXT, non_text=NonText(type=kind, locator="picture[0]"))


def test_a_picture_becomes_a_marked_placeholder_not_silence() -> None:
    """Invariant 7 and ADR-016. The generator does not exist; the gap is still announced."""
    document = _document(Chapter(title="One", blocks=(_picture(),)))
    rendered = _render(document)

    assert 'type="unknown"' in rendered.markdown
    assert 'status="failed"' in rendered.markdown
    assert 'confidence="0.00"' in rendered.markdown
    assert 'source="model"' in rendered.markdown, "the route that was meant to fill it"
    assert "could not describe" in rendered.markdown
    assert "could not describe" in rendered.plain_text, "the listener hears the gap too"
    assert rendered.failed_description_count == 1


def test_a_picture_keeps_its_position_in_reading_order() -> None:
    document = _document(
        Chapter(
            title="One",
            blocks=(
                Block(BlockKind.PARAGRAPH, "Before."),
                _picture(),
                Block(BlockKind.PARAGRAPH, "After."),
            ),
        )
    )
    text = _render(document).plain_text
    assert text.index("Before.") < text.index("could not describe") < text.index("After.")


def test_a_cleanly_extracted_table_renders_from_its_structure() -> None:
    """ARCHITECTURE 4.6: the cells beat a picture of the cells, and no model is involved."""
    cells = (("Name", "Year"), ("Ada", "1843"), ("Grace", "1952"))
    block = Block(
        kind=BlockKind.NON_TEXT,
        non_text=NonText(type=DescriptionType.TABLE, locator="table[0]", table=cells),
    )
    rendered = _render(_document(Chapter(title="One", blocks=(block,))))

    assert 'type="table"' in rendered.markdown
    assert 'status="ok"' in rendered.markdown
    assert 'confidence="1.00"' in rendered.markdown
    # The pair is the point: 1.00 from the cells is not the same claim as 1.00 from a model, and
    # a consumer sorting by confidence needs to tell them apart.
    assert 'source="structure"' in rendered.markdown
    assert "Ada" in rendered.plain_text and "1843" in rendered.plain_text
    assert "|" not in rendered.plain_text, "a pipe table would be read aloud as pipes"
    assert rendered.failed_description_count == 0


def test_a_table_docling_could_not_extract_becomes_a_placeholder() -> None:
    """Half a table rendered as if whole is worse than an announced gap."""
    block = Block(
        kind=BlockKind.NON_TEXT,
        non_text=NonText(type=DescriptionType.TABLE, locator="table[0]", table=None),
    )
    rendered = _render(_document(Chapter(title="One", blocks=(block,))))

    assert 'type="table"' in rendered.markdown
    assert 'status="failed"' in rendered.markdown


def test_every_description_type_has_a_readable_placeholder() -> None:
    """A missing entry would be a KeyError mid-conversion, on a book that reached the end."""
    for kind in DescriptionType:
        rendered = _render(_document(Chapter(title=None, blocks=(_picture(kind),))))
        assert "could not describe" in rendered.plain_text
        assert f'type="{kind.value}"' in rendered.markdown
        assert DescriptionStatus.FAILED.value in rendered.markdown


# --- Exporter and the parse-to-emit assertion --------------------------------------------------


def test_export_writes_both_artifacts(tmp_path: Path) -> None:
    document = _document(Chapter(title="One", blocks=(Block(BlockKind.PARAGRAPH, "Body."),)))
    artifacts = write(_render(document), tmp_path, "book")

    markdown = artifacts.markdown_path.read_text(encoding="utf-8")
    assert markdown == f"{HEADER}\n\n# One\n\nBody.\n"
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
        write(_render(document), tmp_path, "book")


def test_chapter_count_mismatch_aborts_before_writing() -> None:
    """The assertion CLAUDE.md section 4 requires between parse and emit."""
    from asoy import orchestrator

    document = _document(
        Chapter(title="One", blocks=()),
        Chapter(title="Two", blocks=()),
    )
    with pytest.raises(ChapterCountMismatch):
        orchestrator._assert_chapter_counts(document, f"{HEADER}\n\n# One\n", rendered_count=2)


def test_chapter_count_mismatch_on_rendered_count() -> None:
    from asoy import orchestrator

    document = _document(Chapter(title="One", blocks=()))
    with pytest.raises(ChapterCountMismatch):
        orchestrator._assert_chapter_counts(document, f"{HEADER}\n\n# One\n", rendered_count=5)


# --- End to end ---------------------------------------------------------------------------------


def test_text_only_epub_converts_end_to_end(two_chapter_epub: Path, tmp_path: Path) -> None:
    result = convert(two_chapter_epub, tmp_path)

    markdown = result.artifacts.markdown_path.read_text(encoding="utf-8")
    assert markdown.splitlines()[0].startswith("<!-- asoy:document ")
    assert "# The First Chapter" in markdown
    assert "# The Second Chapter" in markdown
    assert "## A Subsection" in markdown
    assert VERBATIM_SENTENCE in markdown
    assert MISSPELLED_SENTENCE in markdown
    assert count_chapter_headings(markdown) == 2
    assert result.artifacts.chapter_count == 2

    flattened = result.artifacts.text_path.read_text(encoding="utf-8")
    assert VERBATIM_SENTENCE in flattened
    assert "<!--" not in flattened
    assert not flattened.startswith("#")


def test_the_document_header_records_the_tier_the_job_ran_on(
    two_chapter_epub: Path, tmp_path: Path
) -> None:
    """Invariant 8, as a property of the output file rather than only of the interface."""
    from asoy.tiers import Tier

    result = convert(two_chapter_epub, tmp_path, tier=Tier.CPU)
    header = result.artifacts.markdown_path.read_text(encoding="utf-8").splitlines()[0]

    assert result.tier is Tier.CPU
    assert f'model="{result.model}"' in header
    # ADR-025 fixes the spelling as part of the contract; Tier is spelled for a human reading the
    # interface. A consumer parses the header, so the header's spelling is the one that is fixed.
    assert 'tier="cpu"' in header


def test_text_only_odt_converts_without_calibre(tmp_path: Path) -> None:
    """ADR-023: ODT is parsed by Docling directly, so no external program is involved."""
    book = build_odt(tmp_path / "book.odt", ODT_TWO_CHAPTERS)
    result = convert(book, tmp_path / "out")

    assert result.decision.route is Route.DIRECT

    markdown = result.artifacts.markdown_path.read_text(encoding="utf-8")
    assert "# The First Chapter" in markdown
    assert "# The Second Chapter" in markdown
    assert VERBATIM_SENTENCE in markdown
    assert count_chapter_headings(markdown) == 2


def test_only_the_defined_delimiter_appears(two_chapter_epub: Path, tmp_path: Path) -> None:
    """ADR-025 settled one shape. None of the shapes it rejected may appear alongside it."""
    result = convert(two_chapter_epub, tmp_path)
    markdown = result.artifacts.markdown_path.read_text(encoding="utf-8")
    for shape in ("[[", "]]", "<description", "{{", "::description", "```asoy", ":::"):
        assert shape not in markdown


def test_drm_protected_book_is_refused_end_to_end(tmp_path: Path) -> None:
    book = build_epub(tmp_path / "drm.epub", [("ch1", CHAPTER_ONE)])
    add_encryption_xml(book, CONTENT_ENCRYPTION_ALGORITHM)

    with pytest.raises(ConversionRefused) as excinfo:
        convert(book, tmp_path / "out")

    assert "DRM" in str(excinfo.value)
    assert not (tmp_path / "out").exists(), "nothing may be written for a refused book"


def test_calibre_path_fails_loudly_rather_than_silently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invariant 5. A Kindle book without Calibre is reported, never approximated.

    The rest of the Calibre path lives in test_calibre.py. This one stays here because it guards
    the orchestrator's contract: nothing is written when the conversion cannot happen.
    """
    monkeypatch.setenv(PATH_ENV_VAR, str(tmp_path / "no-calibre-here.exe"))
    monkeypatch.setattr("asoy.router.ebook_convert.INSTALL_DIRS", ())
    monkeypatch.setattr("shutil.which", lambda _name: None)

    book = build_mobi(tmp_path / "book.azw3", encryption=0)
    with pytest.raises(CalibreNotFound):
        convert(book, tmp_path / "out")

    assert not (tmp_path / "out").exists()


def test_a_document_with_a_picture_and_a_table_converts(tmp_path: Path) -> None:
    """ADR-025 lifted the refusal. Nothing is dropped and nothing is silent (invariant 7).

    A real EPUB carrying a real PNG and a real table, so this exercises Docling's reading order
    rather than a hand-built document that assumes it.
    """
    book = build_epub_with_picture_and_table(tmp_path / "mixed.epub")
    result = convert(book, tmp_path / "out")

    markdown = result.artifacts.markdown_path.read_text(encoding="utf-8")
    flattened = result.artifacts.text_path.read_text(encoding="utf-8")

    assert result.artifacts.description_count == 2
    assert result.artifacts.failed_description_count == 1, "the picture; the table was extracted"

    assert 'type="unknown"' in markdown and 'status="failed"' in markdown
    assert 'type="table"' in markdown and 'status="ok"' in markdown
    assert 'source="structure"' in markdown and 'source="model"' in markdown
    assert "Ada" in markdown and "1843" in markdown

    assert "Before the picture." in flattened
    assert "could not describe" in flattened
    assert "After the table." in flattened
    assert "<!--" not in flattened


def test_non_text_blocks_keep_their_place_in_the_real_reading_order(tmp_path: Path) -> None:
    """A description read out at the wrong moment is worse than the silence it replaced."""
    book = build_epub_with_picture_and_table(tmp_path / "mixed.epub")
    flattened = convert(book, tmp_path / "out").artifacts.text_path.read_text(encoding="utf-8")

    positions = [
        flattened.index("Before the picture."),
        flattened.index("could not describe"),
        flattened.index("Between."),
        flattened.index("A table of"),
        flattened.index("After the table."),
    ]
    assert positions == sorted(positions)


def test_the_emitted_markdown_parses_back(tmp_path: Path) -> None:
    """The round trip, run against a real conversion rather than a constructed document."""
    from asoy.fences import parse as parse_fences
    from asoy.fences import render as render_fences

    book = build_epub_with_picture_and_table(tmp_path / "mixed.epub")
    markdown = convert(book, tmp_path / "out").artifacts.markdown_path.read_text(encoding="utf-8")

    assert render_fences(parse_fences(markdown)) == markdown
