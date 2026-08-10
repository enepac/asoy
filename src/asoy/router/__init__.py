"""Format Router: input dispatch and the Calibre subprocess boundary (ARCHITECTURE section 4.3).

The router decides one of three paths for an input file: straight to Docling, through Calibre
first, or rejected. It performs the DRM check that invariant 2 requires at ingestion.

**The Calibre boundary is a licensing boundary, not a convenience.** Calibre is GPLv3 and Asoy is
Apache 2.0; the command-line subprocess is what keeps those compatible (ADR-010, invariant 5).
This module names the Calibre path but does not invoke it, and when it is implemented it must be
invoked as a subprocess. Importing, linking, or vendoring Calibre relicenses the whole project.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from asoy.router.drm import DrmFinding, inspect

# ARCHITECTURE section 4.3. Formats Docling reads itself.
DIRECT_FORMATS = frozenset(
    {
        ".epub",
        ".pdf",
        ".docx",
        ".pptx",
        ".xlsx",
        ".html",
        ".htm",
        ".txt",
        ".md",
        ".png",
        ".jpg",
        ".jpeg",
        ".tif",
        ".tiff",
        ".bmp",
    }
)

# Formats that must be converted to EPUB by Calibre first. ODT and RTF sit here per section 4.3
# even though Docling lists ODT support, because the routing table is the specification.
CALIBRE_FORMATS = frozenset(
    {
        ".mobi",
        ".azw",
        ".azw3",
        ".fb2",
        ".lit",
        ".pdb",
        ".rtf",
        ".odt",
    }
)


class Route(StrEnum):
    """Where an input goes next."""

    DIRECT = "direct"
    CALIBRE = "calibre"
    REJECTED = "rejected"


class RejectionReason(StrEnum):
    """Why an input was refused. NONE when it was not."""

    NONE = "none"
    DRM_PROTECTED = "drm_protected"
    UNSUPPORTED_FORMAT = "unsupported_format"
    MISSING = "missing"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class RoutingDecision:
    """Where an input goes, and why."""

    route: Route
    suffix: str
    reason: RejectionReason
    detail: str
    remedy: str

    @property
    def accepted(self) -> bool:
        return self.route is not Route.REJECTED


class CalibreConversionNotImplemented(NotImplementedError):
    """Raised when a file needs Calibre, which is not wired up yet.

    Deliberately loud. Silently producing an empty or partial conversion for a Kindle book would
    look like success, and CLAUDE.md section 6 requires failures to be surfaced, never swallowed.
    """


def _reject(
    suffix: str, reason: RejectionReason, detail: str, remedy: str
) -> RoutingDecision:
    return RoutingDecision(
        route=Route.REJECTED, suffix=suffix, reason=reason, detail=detail, remedy=remedy
    )


def route(path: Path) -> RoutingDecision:
    """Decide the path for an input file. Never raises; problems come back as rejections."""
    suffix = path.suffix.lower()

    if not path.exists():
        return _reject(
            suffix,
            RejectionReason.MISSING,
            f"No file exists at {path}.",
            "Check the path and try again.",
        )

    if not path.is_file():
        return _reject(
            suffix,
            RejectionReason.MISSING,
            f"{path} is not a file.",
            "Choose a book file rather than a folder.",
        )

    known = suffix in DIRECT_FORMATS or suffix in CALIBRE_FORMATS
    if not known:
        return _reject(
            suffix,
            RejectionReason.UNSUPPORTED_FORMAT,
            f"Asoy does not read {suffix or 'files without an extension'}.",
            "See the supported formats list in SUPPORT.md.",
        )

    # Invariant 2: the DRM check happens at ingestion, before any conversion work begins, and
    # applies to every format rather than only the ones Calibre would handle.
    try:
        finding: DrmFinding = inspect(path)
    except OSError as exc:
        return _reject(
            suffix,
            RejectionReason.UNREADABLE,
            f"Could not read {path} ({type(exc).__name__}: {exc}).",
            "Check the file is not open in another program, then try again.",
        )

    if finding.protected:
        return _reject(
            suffix,
            RejectionReason.DRM_PROTECTED,
            finding.detail,
            (
                "Asoy cannot convert DRM-protected books, by design, and this is not a bug. "
                "Use a copy you can already open without the vendor's reader application. "
                "See the DRM section in SUPPORT.md."
            ),
        )

    if suffix in CALIBRE_FORMATS:
        return RoutingDecision(
            route=Route.CALIBRE,
            suffix=suffix,
            reason=RejectionReason.NONE,
            detail=f"{suffix} is converted to EPUB by Calibre before parsing.",
            remedy="",
        )

    return RoutingDecision(
        route=Route.DIRECT,
        suffix=suffix,
        reason=RejectionReason.NONE,
        detail=f"{suffix} is parsed directly by Docling.",
        remedy="",
    )
