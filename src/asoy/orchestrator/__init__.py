"""Conversion Orchestrator: job state machine and checkpoints (ARCHITECTURE section 4.2).

Currently the minimum path: route, parse, assemble, export, for a text-only document. Checkpoint
and resume (ADR-015) are not implemented yet.

Two refusals here are deliberate and must not be softened into warnings:

* A document containing non-text blocks is refused, because generating their descriptions is not
  implemented and the delimiter that would mark them is an undefined public interface (ADR-006).
  Emitting the book without them would drop content silently, which is the failure CLAUDE.md
  section 9 names explicitly.
* A chapter-count mismatch between what was parsed and what was rendered aborts the job. Silent
  truncation is indistinguishable from success once the file is on disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from asoy.assemble import count_chapter_headings, render
from asoy.export import WrittenArtifacts, write
from asoy.parser import ParsedDocument, parse
from asoy.router import CalibreConversionNotImplemented, Route, RoutingDecision, route


class ConversionRefused(RuntimeError):
    """The input will not be converted, with a reason the user can act on."""

    def __init__(self, detail: str, remedy: str = "") -> None:
        super().__init__(detail if not remedy else f"{detail} {remedy}")
        self.detail = detail
        self.remedy = remedy


class ChapterCountMismatch(RuntimeError):
    """Parsed and emitted chapter counts disagree. The job aborts rather than writing."""


@dataclass(frozen=True)
class ConversionResult:
    source: Path
    decision: RoutingDecision
    document: ParsedDocument
    artifacts: WrittenArtifacts


def _assert_chapter_counts(document: ParsedDocument, markdown: str, rendered_count: int) -> None:
    """The parse-to-emit assertion. See CLAUDE.md section 4, output writing."""
    if rendered_count != document.chapter_count:
        raise ChapterCountMismatch(
            f"Parsed {document.chapter_count} chapters but rendered {rendered_count}."
        )

    headings = count_chapter_headings(markdown)
    if headings != document.titled_chapter_count:
        raise ChapterCountMismatch(
            f"Parsed {document.titled_chapter_count} titled chapters but the Markdown "
            f"contains {headings} chapter headings."
        )


def convert(source: Path, output_dir: Path) -> ConversionResult:
    """Convert one document to Markdown and flattened text."""
    decision = route(source)

    if decision.route is Route.REJECTED:
        raise ConversionRefused(decision.detail, decision.remedy)

    if decision.route is Route.CALIBRE:
        raise CalibreConversionNotImplemented(
            f"{decision.suffix} requires Calibre, which is not wired up yet. "
            "Calibre must be invoked as a subprocess when it is (ADR-010, invariant 5)."
        )

    document = parse(source)

    if document.undescribed:
        kinds = ", ".join(sorted({block.kind for block in document.undescribed}))
        raise ConversionRefused(
            f"{source.name} contains {len(document.undescribed)} non-text blocks ({kinds}) "
            "that need generated descriptions, which is not implemented yet.",
            "Only text-only documents convert at this stage. Nothing was written.",
        )

    rendered = render(document)
    _assert_chapter_counts(document, rendered.markdown, rendered.chapter_count)

    artifacts = write(rendered, output_dir, source.stem)
    return ConversionResult(
        source=source, decision=decision, document=document, artifacts=artifacts
    )
