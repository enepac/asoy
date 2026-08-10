"""The Calibre subprocess boundary (ARCHITECTURE section 4.3, ADR-010, invariant 5).

Calibre is GPLv3 and Asoy is Apache 2.0. What keeps those compatible is that Calibre never enters
this process: it is a separate program, started over the command line, communicating through
argv, a file on disk, and an exit code. That is an arm's-length boundary rather than a derivative
work, and it is the only reason the formats below can be supported at all.

**Nothing here may soften that.** No Calibre Python package, no plugin loading, no reading of its
internals, and no in-process fallback when the executable is absent. If the program is not there,
the correct behaviour is to say where to get it and stop. This module is named for the command it
runs rather than for the project that ships it, so that the boundary reads correctly in an import
list and in a stack trace.

DRM is rejected at ingestion, before anything here runs (invariant 2, ADR-014). Calibre is only
ever asked to convert files the user can already open, and its own converter does not strip DRM
either — that is plugin territory, and it stays out.

Failures are surfaced with the subprocess's own stderr attached (CLAUDE.md section 6). A
conversion that fails silently, or that reports success while producing nothing, is the failure
mode this module is written to make impossible.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

EXECUTABLE_NAME = "ebook-convert"

# Support answer for a non-standard install location, so "Calibre is somewhere else" is a setting
# rather than a code change. Mirrors OLLAMA_HOST in asoy.environment.
PATH_ENV_VAR = "ASOY_EBOOK_CONVERT"

DOWNLOAD_URL = "https://calibre-ebook.com/download_windows"

# Calibre's Windows installer does not put itself on PATH by default, so the usual install
# locations are checked as well. Anything found is still only ever started as a subprocess.
INSTALL_DIRS = (
    r"C:\Program Files\Calibre2",
    r"C:\Program Files\Calibre",
    r"C:\Program Files (x86)\Calibre2",
    r"C:\Program Files (x86)\Calibre",
)

# A large MOBI takes a while, and a hung job with no ceiling is worse than a reported timeout.
TIMEOUT_SECONDS = 900.0

# Enough of the subprocess's output to diagnose the failure, without pasting a whole build log
# into a message box.
STDERR_TAIL_LINES = 40

_NOT_FOUND_REMEDY = (
    f"Install Calibre from {DOWNLOAD_URL}, then run Asoy again. Asoy runs it as a separate "
    "command-line program and does not bundle it. If Calibre is already installed somewhere "
    f"unusual, set {PATH_ENV_VAR} to the full path of {EXECUTABLE_NAME}.exe."
)


class CalibreError(RuntimeError):
    """A failure on the Calibre path, carrying something the user can act on."""

    def __init__(self, detail: str, remedy: str = "") -> None:
        super().__init__(detail if not remedy else f"{detail} {remedy}")
        self.detail = detail
        self.remedy = remedy


class CalibreNotFound(CalibreError):
    """`ebook-convert` is not installed, or not where we can find it."""


class CalibreFailed(CalibreError):
    """`ebook-convert` ran and did not produce a usable EPUB."""


def _candidates() -> list[Path]:
    """Every place worth looking, in priority order."""
    found: list[Path] = []

    override = os.environ.get(PATH_ENV_VAR)
    if override:
        found.append(Path(override))

    on_path = shutil.which(EXECUTABLE_NAME)
    if on_path:
        found.append(Path(on_path))

    suffix = ".exe" if sys.platform == "win32" else ""
    found.extend(Path(directory) / f"{EXECUTABLE_NAME}{suffix}" for directory in INSTALL_DIRS)
    return found


def locate() -> Path | None:
    """Find `ebook-convert`, or return None. Never raises, and never loads anything of Calibre's."""
    for candidate in _candidates():
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            # An unreadable candidate is not an error, it is simply not the one.
            continue
    return None


def _not_found() -> CalibreNotFound:
    override = os.environ.get(PATH_ENV_VAR)
    where = f"{PATH_ENV_VAR} points at {override}, which is not a file" if override else (
        f"It is not on PATH and not in any of the usual install locations "
        f"({', '.join(INSTALL_DIRS)})"
    )
    return CalibreNotFound(
        f"This format needs Calibre's {EXECUTABLE_NAME}, which could not be found. {where}.",
        _NOT_FOUND_REMEDY,
    )


def _tail(text: str) -> str:
    """The last few non-empty lines of subprocess output, for attaching to a message."""
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    if len(lines) <= STDERR_TAIL_LINES:
        return "\n".join(lines)
    return "...\n" + "\n".join(lines[-STDERR_TAIL_LINES:])


def _reported_output(completed: subprocess.CompletedProcess[str]) -> str:
    """What the subprocess said, preferring stderr and falling back to stdout."""
    for stream, label in ((completed.stderr, "stderr"), (completed.stdout, "stdout")):
        tail = _tail(stream or "")
        if tail:
            return f"\n\nCalibre's {label}:\n{tail}"
    return "\n\nCalibre produced no output on stderr or stdout."


def _run(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    # CREATE_NO_WINDOW keeps a console from flashing over the desktop shell on every conversion.
    # It does not exist off Windows, and ADR-007 ships Windows only, so this is a guard for the
    # development and test paths rather than a portability claim.
    extra: dict[str, int] = {}
    no_window = getattr(subprocess, "CREATE_NO_WINDOW", None)
    if no_window is not None:
        extra["creationflags"] = no_window

    return subprocess.run(  # noqa: S603 - a located executable, never a shell string
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        **extra,
    )


def convert_to_epub(
    source: Path, destination: Path, *, timeout: float = TIMEOUT_SECONDS
) -> Path:
    """Convert `source` to an EPUB at `destination` by running `ebook-convert`.

    Returns the destination path. Raises CalibreNotFound if the program is absent, and
    CalibreFailed for every other outcome that is not a readable EPUB — including the one that
    matters most, a zero exit code with nothing written.
    """
    executable = locate()
    if executable is None:
        raise _not_found()

    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [str(executable), str(source), str(destination)]

    try:
        completed = _run(command, timeout)
    except subprocess.TimeoutExpired:
        raise CalibreFailed(
            f"Calibre did not finish converting {source.name} within {timeout:.0f} seconds.",
            "The file may be unusually large or damaged. Try converting it in Calibre directly "
            "to see where it stops.",
        ) from None
    except OSError as exc:
        raise CalibreFailed(
            f"Could not start {executable} ({type(exc).__name__}: {exc}).",
            "Check that Calibre is installed correctly and that the file is not blocked by "
            "security software.",
        ) from exc

    if completed.returncode != 0:
        raise CalibreFailed(
            f"Calibre failed to convert {source.name} (exit code {completed.returncode})."
            f"{_reported_output(completed)}",
            "Opening the file in Calibre directly usually shows the same error with more "
            "context. A file that Calibre cannot convert, Asoy cannot convert either.",
        )

    # A zero exit code is not evidence. Without this check an empty or missing intermediate would
    # reach the parser and fail there, or worse, parse as an empty book and look like a success.
    if not destination.is_file():
        raise CalibreFailed(
            f"Calibre reported success converting {source.name} but wrote no file to "
            f"{destination}.{_reported_output(completed)}",
            "This is unexpected. Please report it, including the output above.",
        )

    if destination.stat().st_size == 0:
        raise CalibreFailed(
            f"Calibre reported success converting {source.name} but the EPUB it wrote is empty."
            f"{_reported_output(completed)}",
            "This is unexpected. Please report it, including the output above.",
        )

    return destination
