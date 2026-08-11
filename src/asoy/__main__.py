"""Console entry point: parses arguments and dispatches into the desktop shell or a conversion."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asoy.tiers import TierDetection

NOT_INSTALLED = (
    "asoy is not installed in this environment. "
    "Run 'uv sync' from the project root, then 'uv run asoy'."
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="asoy",
        description="Convert books into text prepared for audiobook narration.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="print the installed version and exit without opening a window",
    )
    parser.add_argument(
        "--tier",
        action="store_true",
        help="print the detected hardware tier and exit without opening a window",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check the tier and the Ollama environment, then exit; 0 if ready, 1 if not",
    )

    # Not required: running `asoy` with no subcommand still opens the window.
    subcommands = parser.add_subparsers(dest="command")
    convert = subcommands.add_parser(
        "convert",
        help="convert one book and exit, without opening a window",
        description=(
            "Convert one book to Markdown and flattened text. Pictures and tables are marked "
            "in place; until the description generator exists, a picture is emitted as an "
            "explicit placeholder rather than being dropped."
        ),
    )
    convert.add_argument("book", type=Path, help="the book to convert")
    convert.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path.cwd(),
        help="directory to write the .md and .txt into (default: the current directory)",
    )

    subcommands.add_parser(
        "fetch-ocr-models",
        help="download the OCR models needed for scanned PDFs and images, then exit",
        description=(
            "Download the OCR models once, into a directory Asoy controls. Scanned PDFs and "
            "images need them; EPUB, DOCX, and ODT do not. This is the only command that "
            "downloads them — a conversion never does, so that converting a book makes no "
            "network request at all."
        ),
    )
    return parser


def _print_tier() -> TierDetection:
    """Print the detected tier and return it. Invariant 8: the active tier is always visible."""
    from asoy.tiers import detect

    result = detect()
    vram = result.total_vram_gib
    print(f"Tier:   {result.tier.value}")
    print(f"Device: {result.device_name or 'none detected'}")
    print(f"VRAM:   {f'{vram:.2f} GiB' if vram is not None else 'not applicable'}")
    print(f"Reason: {result.reason}")
    return result


def _fail(detail: str, remedy: str = "") -> int:
    print(detail, file=sys.stderr)
    if remedy:
        print(remedy, file=sys.stderr)
    return 1


def _fetch_ocr_models_command() -> int:
    """Download the OCR weights. The one command in Asoy that fetches them (ADR-029)."""
    from asoy.ocr import OcrWeightsMissing, fetch, models_dir, verify

    where = models_dir()
    print(f"OCR models directory: {where}")

    try:
        result = fetch(where)
    except OcrWeightsMissing as exc:
        return _fail(exc.detail, exc.remedy)

    problems = verify(where)
    if problems:
        return _fail(
            "The downloaded OCR models did not verify: " + " ".join(problems),
            "Delete the directory above and run this command again.",
        )

    print()
    print(f"All {len(result.present)} OCR models present and verified.")
    print("Scanned PDFs and images will convert now, without any further download.")
    return 0


def _convert_command(book: Path, output_dir: Path) -> int:
    """Run one conversion. Every failure prints what happened and what to do about it."""
    from asoy.export import OutputVerificationError
    from asoy.fences import FenceError
    from asoy.ocr import OcrWeightsMissing
    from asoy.orchestrator import ChapterCountMismatch, ConversionRefused, convert
    from asoy.parser import ParseError
    from asoy.router.ebook_convert import CalibreError

    # Invariant 8. Output quality depends on the tier, so a job never runs without naming it, and
    # the same detection is handed to the conversion so one job cannot report two answers.
    tier = _print_tier()
    print()

    try:
        result = convert(book, output_dir, tier=tier.tier)
    except (ConversionRefused, CalibreError, OcrWeightsMissing) as exc:
        return _fail(exc.detail, exc.remedy)
    except ParseError as exc:
        return _fail(str(exc), "A file Docling cannot read cannot be converted.")
    except (ChapterCountMismatch, OutputVerificationError, FenceError) as exc:
        return _fail(
            f"The conversion was abandoned before it could produce a misleading file: {exc}",
            "This is a defect in Asoy, not something you can fix. Please report it.",
        )

    artifacts = result.artifacts
    if result.intermediate is not None:
        print("Converted via Calibre to an intermediate EPUB, then parsed.")
    print(f"Chapters: {artifacts.chapter_count}")
    if artifacts.description_count:
        print(
            f"Described: {artifacts.description_count} non-text blocks, "
            f"{artifacts.failed_description_count} marked as placeholders"
        )
    if artifacts.gated_table_count:
        print(
            f"Tables:    {artifacts.gated_table_count} had structure too damaged to narrate and "
            "were passed on for description instead"
        )
    print(f"Markdown: {artifacts.markdown_path}")
    print(f"Text:     {artifacts.text_path}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI. With a flag or a subcommand, do that and exit; otherwise open the shell."""
    args = _build_parser().parse_args(argv)

    try:
        installed = version("asoy")
    except PackageNotFoundError:
        print(NOT_INSTALLED, file=sys.stderr)
        return 1

    if args.version:
        print(f"asoy {installed}")
        return 0

    if args.command == "fetch-ocr-models":
        return _fetch_ocr_models_command()

    if args.command == "convert":
        return _convert_command(args.book, args.output)

    if args.tier or args.check:
        result = _print_tier()

        if not args.check:
            return 0

        from asoy.environment import check as check_environment

        environment = check_environment(result.tier)
        print()
        print(f"Status: {'ready' if environment.ok else 'not ready'}")
        print(f"Detail: {environment.detail}")
        if environment.remedy:
            print(f"Remedy: {environment.remedy}")
        return 0 if environment.ok else 1

    from asoy.shell import run_window

    return run_window(installed)


if __name__ == "__main__":
    raise SystemExit(main())
