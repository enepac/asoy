"""Assembler: emits canonical Markdown from the parsed document (ARCHITECTURE section 4.8).

Author text is transcribed verbatim (invariant 3) and chapter structure is preserved as headings
(ADR-005). Only the structural characters this module adds, the `#` of a heading and the blank
line between blocks, are Asoy's; every other character in the output came from the author.

**No description delimiter is emitted here.** The delimiter is a public interface (ADR-006) and is
not yet defined, so this module refuses to render a document containing non-text blocks rather
than inventing a shape or, worse, dropping them. That refusal lives in the orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass

from asoy.parser import Block, BlockKind, Chapter, ParsedDocument

CHAPTER_HEADING_LEVEL = 1


@dataclass(frozen=True)
class RenderedDocument:
    """The rendered artifacts, plus the chapter count the renderer actually emitted."""

    markdown: str
    plain_text: str
    chapter_count: int
    titled_chapter_count: int


def _markdown_block(block: Block) -> str:
    if block.kind is BlockKind.HEADING:
        return f"{'#' * block.level} {block.text}"
    return block.text


def _plain_block(block: Block) -> str:
    # The flattened export carries no structural markers at all (section 4.9).
    return block.text


def _chapter_parts(chapter: Chapter, *, markdown: bool) -> list[str]:
    parts: list[str] = []
    if chapter.title is not None:
        heading = f"{'#' * CHAPTER_HEADING_LEVEL} {chapter.title}" if markdown else chapter.title
        parts.append(heading)
    render = _markdown_block if markdown else _plain_block
    parts.extend(render(block) for block in chapter.blocks)
    return parts


def render(document: ParsedDocument) -> RenderedDocument:
    """Render the parsed document to Markdown and to flattened plain text."""
    markdown_parts: list[str] = []
    plain_parts: list[str] = []
    for chapter in document.chapters:
        markdown_parts.extend(_chapter_parts(chapter, markdown=True))
        plain_parts.extend(_chapter_parts(chapter, markdown=False))

    markdown = "\n\n".join(markdown_parts)
    plain_text = "\n\n".join(plain_parts)

    return RenderedDocument(
        markdown=markdown + "\n" if markdown else "",
        plain_text=plain_text + "\n" if plain_text else "",
        chapter_count=len(document.chapters),
        titled_chapter_count=document.titled_chapter_count,
    )


def count_chapter_headings(markdown: str) -> int:
    """Count top-level headings in rendered Markdown. Used by the parse-to-emit assertion."""
    marker = f"{'#' * CHAPTER_HEADING_LEVEL} "
    return sum(1 for line in markdown.splitlines() if line.startswith(marker))
