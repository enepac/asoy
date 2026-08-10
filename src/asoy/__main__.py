"""Console entry point: parses arguments and dispatches into the desktop shell."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version

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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI. With --version, print and exit; otherwise open the shell window."""
    args = _build_parser().parse_args(argv)

    try:
        installed = version("asoy")
    except PackageNotFoundError:
        print(NOT_INSTALLED, file=sys.stderr)
        return 1

    if args.version:
        print(f"asoy {installed}")
        return 0

    if args.tier:
        from asoy.tiers import detect

        result = detect()
        vram = result.total_vram_gib
        print(f"Tier:   {result.tier.value}")
        print(f"Device: {result.device_name or 'none detected'}")
        print(f"VRAM:   {f'{vram:.2f} GiB' if vram is not None else 'not applicable'}")
        print(f"Reason: {result.reason}")
        return 0

    from asoy.shell import run_window

    return run_window(installed)


if __name__ == "__main__":
    raise SystemExit(main())
