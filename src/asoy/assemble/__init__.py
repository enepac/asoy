"""Assembler: emits the canonical Markdown and its flattened form (ARCHITECTURE section 4.8).

Author text is transcribed verbatim (invariant 3) and chapter structure is preserved as headings
(ADR-005). This module translates the parsed document into the fenced document that
`asoy.fences` renders; it does not build markers itself, so the format has exactly one definition
(ADR-025).

**Non-text blocks are never dropped.** Every picture and table becomes a description fence in its
reading position. The description generator does not exist yet, so a picture becomes a `failed`
description carrying readable placeholder text — a marked gap, never silence (invariant 7,
ADR-016). A table whose structure Docling extracted cleanly is rendered from that structure
instead, which is faster and more accurate than describing a picture of a table (section 4.6).
"""

from __future__ import annotations

from dataclasses import dataclass

from asoy.fences import (
    CHAPTER_HEADING_LEVEL,
    AuthorSegment,
    DescriptionSegment,
    DescriptionStatus,
    DescriptionType,
    DocumentHeader,
    FencedDocument,
    HeadingSegment,
    Segment,
    flatten,
)
from asoy.fences import (
    render as render_markdown,
)
from asoy.parser import Block, BlockKind, Chapter, NonText, ParsedDocument

# What a listener hears where a description could not be produced. Written to be heard: a full
# sentence, no markup, and it says which kind of thing is missing so the gap is intelligible.
PLACEHOLDER = {
    DescriptionType.PHOTOGRAPH: "A photograph appears here that Asoy could not describe.",
    DescriptionType.ILLUSTRATION: "An illustration appears here that Asoy could not describe.",
    DescriptionType.TABLE: "A table appears here that Asoy could not describe.",
    DescriptionType.DIAGRAM: "A diagram appears here that Asoy could not describe.",
    DescriptionType.CHART: "A chart appears here that Asoy could not describe.",
    DescriptionType.UNKNOWN: "A visual element appears here that Asoy could not describe.",
}

# A structurally rendered table involved no model and no heuristic, so there is nothing to be
# uncertain about: the cells are the cells. Confidence records that, rather than inventing a
# number to look consistent with descriptions that were guessed at.
STRUCTURAL_CONFIDENCE = 1.00

# No description has been generated, so nothing has been judged. Not a low score — an absent one.
FAILED_CONFIDENCE = 0.00


@dataclass(frozen=True)
class RenderedDocument:
    """The rendered artifacts, plus the chapter count the renderer actually emitted."""

    markdown: str
    plain_text: str
    chapter_count: int
    titled_chapter_count: int
    description_count: int
    failed_description_count: int


def render_table(rows: tuple[tuple[str, ...], ...]) -> str:
    """Render a table's cells as prose meant to be heard.

    A pipe table is the obvious Markdown rendering and the wrong one here: the flattened `.txt`
    would carry the pipes into a narration, and a listener has no column to look back at. Naming
    each column as its value is read is what makes a table followable by ear.
    """
    header, *body = rows
    columns = [cell or f"column {index + 1}" for index, cell in enumerate(header)]

    lines = [
        f"A table of {len(columns)} columns and {len(body)} rows. "
        f"The columns are: {', '.join(columns)}."
    ]
    for number, row in enumerate(body, start=1):
        cells = [
            f"{columns[index] if index < len(columns) else f'column {index + 1}'}, {value}"
            for index, value in enumerate(row)
            if value
        ]
        lines.append(f"Row {number}. {'. '.join(cells)}." if cells else f"Row {number} is empty.")
    return "\n".join(lines)


def _description_for(non_text: NonText) -> DescriptionSegment:
    """The description fence one non-text block becomes."""
    if non_text.table:
        return DescriptionSegment(
            type=DescriptionType.TABLE,
            confidence=STRUCTURAL_CONFIDENCE,
            status=DescriptionStatus.OK,
            body=render_table(non_text.table),
        )

    return DescriptionSegment(
        type=non_text.type,
        confidence=FAILED_CONFIDENCE,
        status=DescriptionStatus.FAILED,
        body=PLACEHOLDER[non_text.type],
    )


def _segments_for(block: Block) -> Segment:
    if block.kind is BlockKind.NON_TEXT:
        assert block.non_text is not None  # noqa: S101 - the kind is the invariant
        return _description_for(block.non_text)
    if block.kind is BlockKind.HEADING:
        return HeadingSegment(level=block.level, text=block.text)
    return AuthorSegment(text=block.text)


def _chapter_segments(chapter: Chapter) -> list[Segment]:
    segments: list[Segment] = []
    if chapter.title is not None:
        segments.append(HeadingSegment(level=CHAPTER_HEADING_LEVEL, text=chapter.title))
    segments.extend(_segments_for(block) for block in chapter.blocks)
    return segments


def to_fenced(document: ParsedDocument, *, tier: str, model: str) -> FencedDocument:
    """Translate the parsed document into the document the fence module renders."""
    segments: list[Segment] = []
    for chapter in document.chapters:
        segments.extend(_chapter_segments(chapter))
    return FencedDocument(
        header=DocumentHeader(tier=tier, model=model), segments=tuple(segments)
    )


def render(document: ParsedDocument, *, tier: str, model: str) -> RenderedDocument:
    """Render the parsed document to Markdown and to flattened plain text."""
    fenced = to_fenced(document, tier=tier, model=model)
    descriptions = [s for s in fenced.segments if isinstance(s, DescriptionSegment)]

    return RenderedDocument(
        markdown=render_markdown(fenced),
        plain_text=flatten(fenced),
        chapter_count=len(document.chapters),
        titled_chapter_count=document.titled_chapter_count,
        description_count=len(descriptions),
        failed_description_count=sum(
            1 for s in descriptions if s.status is DescriptionStatus.FAILED
        ),
    )


def count_chapter_headings(markdown: str) -> int:
    """Count top-level headings in a rendered artifact. Used by the parse-to-emit assertion.

    This parses rather than scanning for lines beginning with a hash. Since ADR-025, author text
    that begins with a hash is legal and is wrapped in a text fence, so a line scan would count
    the author's characters as Asoy's structure — which is the exact confusion the format exists
    to prevent, and would make the assertion fire on a correct conversion.
    """
    from asoy.fences import parse

    return parse(markdown).chapter_count
