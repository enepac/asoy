"""Console entry point. Prints the installed version; the shell is not implemented yet."""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version


def main() -> int:
    """Print the installed version and exit, returning a process exit code."""
    try:
        installed = version("asoy")
    except PackageNotFoundError:
        print(
            "asoy is not installed in this environment. "
            "Run 'uv sync' from the project root, then 'uv run asoy'.",
            file=sys.stderr,
        )
        return 1

    print(f"asoy {installed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
