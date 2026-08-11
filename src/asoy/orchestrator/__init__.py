"""Conversion Orchestrator: job state machine and checkpoints (ARCHITECTURE section 4.2).

Currently the minimum path: route, convert if the format needs Calibre, parse, assemble, export,
for a text-only document. Checkpoint and resume (ADR-015) are not implemented yet.

Formats on the Calibre row of the routing table are converted to an EPUB inside a per-job temp
directory, which is removed when the job ends either way (ARCHITECTURE section 7). The user's
source file is never moved, copied over, or modified.

Documents containing pictures and tables now convert. Until ADR-025 defined the delimiter there
was nothing to mark a description with, so the only honest option was refusal; a picture now
becomes a `failed` description carrying placeholder text, which is a marked gap rather than a
silent drop (invariant 7). That is interim behaviour, correct rather than finished — it stops
being interim when the description generator exists.

One refusal here is deliberate and must not be softened into a warning: a chapter-count mismatch
between what was parsed and what was rendered aborts the job. Silent truncation is
indistinguishable from success once the file is on disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from asoy.assemble import count_chapter_headings, render
from asoy.environment import model_tag_for
from asoy.export import WrittenArtifacts, write
from asoy.parser import ParsedDocument, parse
from asoy.router import Route, RoutingDecision, route
from asoy.router.ebook_convert import convert_to_epub
from asoy.tiers import Tier, detect

# Working files live here for the life of the job and no longer (ARCHITECTURE section 7).
TEMP_PREFIX = "asoy-job-"


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
    # Invariant 8: the tier a job ran on is recorded, not only shown. It is also in the header of
    # the emitted Markdown, so an output file can always be traced to what produced it.
    tier: Tier
    model: str
    # The intermediate EPUB Calibre produced, for the job record. None on the direct path. The
    # path itself no longer exists by the time this is returned; the temp directory is gone.
    intermediate: Path | None = None


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


def convert(source: Path, output_dir: Path, *, tier: Tier | None = None) -> ConversionResult:
    """Convert one document to Markdown and flattened text.

    `tier` is detected if not supplied. A caller that has already detected it — the CLI prints it
    before starting, the shell shows it — passes it in so one job never reports two answers.
    """
    resolved = tier if tier is not None else detect().tier
    model = model_tag_for(resolved)

    decision = route(source)

    if decision.route is Route.REJECTED:
        raise ConversionRefused(decision.detail, decision.remedy)

    if decision.route is Route.CALIBRE:
        with TemporaryDirectory(prefix=TEMP_PREFIX) as work_dir:
            intermediate = convert_to_epub(source, Path(work_dir) / f"{source.stem}.epub")
            return _parse_and_write(source, decision, intermediate, output_dir, resolved, model)

    return _parse_and_write(source, decision, source, output_dir, resolved, model)


def _parse_and_write(
    source: Path,
    decision: RoutingDecision,
    parse_target: Path,
    output_dir: Path,
    tier: Tier,
    model: str,
) -> ConversionResult:
    """Parse, assemble, and export. `parse_target` differs from `source` on the Calibre path."""
    document = parse(parse_target)

    # Lowercased for the header. ADR-025 fixes the attribute's spelling as part of the output
    # contract, and `Tier` is spelled for a human reading the interface. Normalising here keeps
    # the file's shape independent of how the enum happens to be written.
    rendered = render(document, tier=tier.value.lower(), model=model)
    _assert_chapter_counts(document, rendered.markdown, rendered.chapter_count)

    artifacts = write(rendered, output_dir, source.stem)
    return ConversionResult(
        source=source,
        decision=decision,
        document=document,
        artifacts=artifacts,
        tier=tier,
        model=model,
        intermediate=None if parse_target == source else parse_target,
    )
