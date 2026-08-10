"""The Calibre subprocess boundary and the convert command (ADR-010, invariant 5).

Nothing here needs Calibre installed. `ebook-convert` is located through ASOY_EBOOK_CONVERT, so
every test points that variable at a small generated `.cmd` that behaves the way a particular
Calibre outcome behaves. That keeps the suite runnable on a clean machine and, more usefully,
lets the failure paths be tested at all — a real Calibre is hard to make fail on demand.

The one thing that cannot be faked is the licensing boundary, so it is asserted directly against
the source tree instead.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import asoy
from asoy.orchestrator import ConversionRefused, convert
from asoy.router import Route, route
from asoy.router.ebook_convert import (
    PATH_ENV_VAR,
    CalibreFailed,
    CalibreNotFound,
    convert_to_epub,
    locate,
)
from tests.epub_fixtures import CHAPTER_ONE, CHAPTER_TWO, build_epub, build_mobi


def _fake_ebook_convert(tmp_path: Path, script: str) -> Path:
    """Write a .cmd standing in for ebook-convert. %1 is the source, %2 the destination."""
    path = tmp_path / "ebook-convert.cmd"
    path.write_text("@echo off\r\n" + script.replace("\n", "\r\n") + "\r\n", encoding="ascii")
    return path


@pytest.fixture
def kindle_book(tmp_path: Path) -> Path:
    return build_mobi(tmp_path / "book.azw3", encryption=0)


# --- Invariant 5: the boundary itself ----------------------------------------------------------


def test_no_module_in_the_package_imports_calibre() -> None:
    """Invariant 5 and ADR-010: Calibre is a subprocess, never a library.

    Scans the whole package rather than the router alone, because the module that actually runs
    `ebook-convert` is the one where the temptation would arrive. Importing Calibre would
    relicense Asoy from Apache 2.0 to GPLv3, silently and retroactively.
    """
    package_root = Path(asoy.__file__).parent
    sources = sorted(package_root.rglob("*.py"))
    assert sources, "the scan found no source files, so it is proving nothing"

    for source in sources:
        text = source.read_text(encoding="utf-8")
        for forbidden in ("import calibre", "from calibre"):
            assert forbidden not in text, f"{source} appears to import Calibre"


def test_conversion_does_not_load_calibre_into_the_process(
    kindle_book: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The static scan cannot see a runtime import. This does."""
    epub = build_epub(tmp_path / "converted.epub", [("ch1", CHAPTER_ONE)])
    fake = _fake_ebook_convert(tmp_path, f'copy /y "{epub}" "%~2" >nul')
    monkeypatch.setenv(PATH_ENV_VAR, str(fake))

    convert(kindle_book, tmp_path / "out")

    assert not [name for name in sys.modules if name == "calibre" or name.startswith("calibre.")]


def test_the_external_program_is_what_does_the_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The boundary is observable: a separate program writes the intermediate, not this process."""
    marker = tmp_path / "ran.txt"
    fake = _fake_ebook_convert(
        tmp_path,
        f'echo ran > "{marker}"\ncopy /y "%~1" "%~2" >nul',
    )
    monkeypatch.setenv(PATH_ENV_VAR, str(fake))

    source = build_epub(tmp_path / "in.epub", [("ch1", CHAPTER_ONE)])
    produced = convert_to_epub(source, tmp_path / "work" / "out.epub")

    assert marker.is_file(), "the external program did not run"
    assert produced.is_file()


# --- Locating it -------------------------------------------------------------------------------


def test_locate_prefers_the_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _fake_ebook_convert(tmp_path, "exit /b 0")
    monkeypatch.setenv(PATH_ENV_VAR, str(fake))
    assert locate() == fake


def test_absent_calibre_is_reported_with_somewhere_to_go(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-008's lesson applied to the second prerequisite: name the fix, do not just refuse."""
    monkeypatch.setenv(PATH_ENV_VAR, str(tmp_path / "definitely-not-here.exe"))
    monkeypatch.setattr("asoy.router.ebook_convert.INSTALL_DIRS", ())
    monkeypatch.setattr("shutil.which", lambda _name: None)

    with pytest.raises(CalibreNotFound) as excinfo:
        convert_to_epub(tmp_path / "book.azw3", tmp_path / "out.epub")

    assert "calibre-ebook.com" in excinfo.value.remedy
    assert PATH_ENV_VAR in excinfo.value.remedy
    assert excinfo.value.detail


def test_locate_returns_none_rather_than_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(PATH_ENV_VAR, raising=False)
    monkeypatch.setattr("asoy.router.ebook_convert.INSTALL_DIRS", ())
    monkeypatch.setattr("shutil.which", lambda _name: None)
    assert locate() is None


# --- Failure paths -----------------------------------------------------------------------------


def test_stderr_is_surfaced_not_swallowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CLAUDE.md section 6. A swallowed stderr makes the failure unexplainable."""
    fake = _fake_ebook_convert(
        tmp_path,
        "echo InputFormatPlugin: no reader for this file 1>&2\nexit /b 1",
    )
    monkeypatch.setenv(PATH_ENV_VAR, str(fake))

    with pytest.raises(CalibreFailed) as excinfo:
        convert_to_epub(tmp_path / "book.azw3", tmp_path / "work" / "out.epub")

    assert "no reader for this file" in excinfo.value.detail
    assert "exit code 1" in excinfo.value.detail
    assert excinfo.value.remedy


def test_stdout_is_surfaced_when_stderr_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _fake_ebook_convert(tmp_path, "echo something went wrong on stdout\nexit /b 2")
    monkeypatch.setenv(PATH_ENV_VAR, str(fake))

    with pytest.raises(CalibreFailed) as excinfo:
        convert_to_epub(tmp_path / "book.azw3", tmp_path / "work" / "out.epub")

    assert "something went wrong on stdout" in excinfo.value.detail


def test_success_with_no_output_file_is_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dangerous one. A zero exit code and no file would parse as an empty book."""
    fake = _fake_ebook_convert(tmp_path, "exit /b 0")
    monkeypatch.setenv(PATH_ENV_VAR, str(fake))

    with pytest.raises(CalibreFailed) as excinfo:
        convert_to_epub(tmp_path / "book.azw3", tmp_path / "work" / "out.epub")

    assert "wrote no file" in excinfo.value.detail


def test_success_with_an_empty_output_file_is_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _fake_ebook_convert(tmp_path, 'type nul > "%~2"\nexit /b 0')
    monkeypatch.setenv(PATH_ENV_VAR, str(fake))

    with pytest.raises(CalibreFailed) as excinfo:
        convert_to_epub(tmp_path / "book.azw3", tmp_path / "work" / "out.epub")

    assert "empty" in excinfo.value.detail


def test_a_hung_conversion_times_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A job that never returns is worse than one that reports a timeout.

    The timeout is raised rather than waited for. A test that really blocks would have to hold
    the suite for the duration to prove anything, and what is under test is the handling.
    """
    monkeypatch.setenv(PATH_ENV_VAR, str(_fake_ebook_convert(tmp_path, "exit /b 0")))

    def expire(command: list[str], timeout: float) -> None:
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr("asoy.router.ebook_convert._run", expire)

    with pytest.raises(CalibreFailed) as excinfo:
        convert_to_epub(tmp_path / "b.azw3", tmp_path / "work" / "out.epub", timeout=900.0)

    assert "within 900 seconds" in excinfo.value.detail
    assert excinfo.value.remedy


# --- End to end through the orchestrator -------------------------------------------------------


def test_kindle_book_converts_through_the_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole Calibre row of the routing table, with a stand-in doing the conversion."""
    epub = build_epub(tmp_path / "converted.epub", [("ch1", CHAPTER_ONE), ("ch2", CHAPTER_TWO)])
    fake = _fake_ebook_convert(tmp_path, f'copy /y "{epub}" "%~2" >nul')
    monkeypatch.setenv(PATH_ENV_VAR, str(fake))

    book = build_mobi(tmp_path / "book.azw3", encryption=0)
    assert route(book).route is Route.CALIBRE

    result = convert(book, tmp_path / "out")

    assert result.source == book
    assert result.intermediate is not None, "the job record must say it went through Calibre"
    markdown = result.artifacts.markdown_path.read_text(encoding="utf-8")
    assert markdown.startswith("# The First Chapter")
    assert result.artifacts.markdown_path.name == "book.md", "output is named for the user's file"


def test_the_intermediate_epub_does_not_outlive_the_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ARCHITECTURE section 7: working files are deleted when the job ends."""
    epub = build_epub(tmp_path / "converted.epub", [("ch1", CHAPTER_ONE)])
    fake = _fake_ebook_convert(tmp_path, f'copy /y "{epub}" "%~2" >nul')
    monkeypatch.setenv(PATH_ENV_VAR, str(fake))

    result = convert(build_mobi(tmp_path / "book.azw3", encryption=0), tmp_path / "out")

    assert result.intermediate is not None
    assert not result.intermediate.exists()
    assert not result.intermediate.parent.exists()


def test_the_source_file_is_never_modified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    epub = build_epub(tmp_path / "converted.epub", [("ch1", CHAPTER_ONE)])
    fake = _fake_ebook_convert(tmp_path, f'copy /y "{epub}" "%~2" >nul')
    monkeypatch.setenv(PATH_ENV_VAR, str(fake))

    book = build_mobi(tmp_path / "book.azw3", encryption=0)
    before = book.read_bytes()
    convert(book, tmp_path / "out")
    assert book.read_bytes() == before


def test_drm_is_still_refused_before_calibre_is_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invariant 2. Wiring up the subprocess must not let a protected file reach it."""
    marker = tmp_path / "ran.txt"
    fake = _fake_ebook_convert(tmp_path, f'echo ran > "{marker}"\nexit /b 0')
    monkeypatch.setenv(PATH_ENV_VAR, str(fake))

    book = build_mobi(tmp_path / "drm.azw3", encryption=2)
    with pytest.raises(ConversionRefused):
        convert(book, tmp_path / "out")

    assert not marker.exists(), "Calibre must never be handed a DRM-protected file"


# --- The convert command -----------------------------------------------------------------------


def test_convert_command_writes_both_artifacts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from asoy.__main__ import main

    book = build_epub(tmp_path / "book.epub", [("ch1", CHAPTER_ONE)])
    out = tmp_path / "out"

    assert main(["convert", str(book), "--output", str(out)]) == 0

    printed = capsys.readouterr().out
    assert "Tier:" in printed, "invariant 8: the active tier is always visible"
    assert (out / "book.md").is_file()
    assert (out / "book.txt").is_file()


def test_convert_command_reports_a_refusal_and_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from asoy.__main__ import main

    odd = tmp_path / "book.xyz"
    odd.write_text("not a book", encoding="utf-8")

    assert main(["convert", str(odd), "--output", str(tmp_path / "out")]) == 1
    assert "does not read" in capsys.readouterr().err


def test_convert_command_reports_missing_calibre(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from asoy.__main__ import main

    monkeypatch.setenv(PATH_ENV_VAR, str(tmp_path / "nope.exe"))
    monkeypatch.setattr("asoy.router.ebook_convert.INSTALL_DIRS", ())
    monkeypatch.setattr("shutil.which", lambda _name: None)

    book = build_mobi(tmp_path / "book.azw3", encryption=0)
    assert main(["convert", str(book), "--output", str(tmp_path / "out")]) == 1

    printed = capsys.readouterr().err
    assert "could not be found" in printed
    assert "calibre-ebook.com" in printed


def test_convert_is_reachable_from_the_installed_entry_point(tmp_path: Path) -> None:
    """The command exists as a command, not only as a Python function."""
    book = build_epub(tmp_path / "book.epub", [("ch1", CHAPTER_ONE)])
    result = subprocess.run(
        [sys.executable, "-m", "asoy", "convert", str(book), "-o", str(tmp_path / "out")],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "out" / "book.md").is_file()


def test_bare_invocation_still_opens_the_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adding a subcommand must not change what plain `asoy` does."""
    from asoy.__main__ import main

    calls: list[str] = []
    monkeypatch.setattr("asoy.shell.run_window", lambda v: calls.append(v) or 0)
    assert main([]) == 0
    assert len(calls) == 1
