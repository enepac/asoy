"""Smoke tests: the package imports, the skeleton is intact, and the entry point runs.

These guard the scaffold itself. They catch a component package being renamed or dropped
without ARCHITECTURE section 4 being updated alongside it, and a frontend asset going
missing from the wheel.

Nothing here opens a window. A GUI test needs a display, so it cannot run headless or in CI,
and a test that blocks on a window is worse than no test at all. Every invocation of the CLI
below passes --version, which is the documented non-windowed path.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest

import asoy
from asoy.__main__ import main
from asoy.shell import ShellApi, run_window

# One entry per component in ARCHITECTURE section 4, plus tier detection from section 5.
COMPONENT_MODULES = [
    "asoy.shell",
    "asoy.orchestrator",
    "asoy.router",
    "asoy.parser",
    "asoy.ocr",
    "asoy.classifier",
    "asoy.describe",
    "asoy.assemble",
    "asoy.export",
    "asoy.tiers",
]

WEB_ASSETS = ["index.html", "style.css", "app.js"]


def test_package_imports() -> None:
    assert asoy.__name__ == "asoy"


@pytest.mark.parametrize("module_name", COMPONENT_MODULES)
def test_component_module_imports(module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert module.__doc__, f"{module_name} must carry a docstring naming its component"


def test_version_flag_reports_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"asoy {version('asoy')}"


def test_module_entry_point_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "asoy", "--version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("asoy ")


def test_unknown_argument_is_rejected() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--nonsense"])
    assert excinfo.value.code != 0


def test_shell_api_reports_the_version_it_was_given() -> None:
    """The frontend reads the version over this bridge method. No window involved."""
    assert ShellApi("1.2.3").get_version() == "1.2.3"


def test_run_window_is_not_called_by_the_version_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guards the hang: --version must never reach the blocking window call."""
    calls: list[str] = []
    monkeypatch.setattr("asoy.shell.run_window", lambda v: calls.append(v) or 0)
    assert main(["--version"]) == 0
    assert calls == []


@pytest.mark.parametrize("asset", WEB_ASSETS)
def test_frontend_asset_present(asset: str) -> None:
    web_dir = Path(asoy.__file__).parent / "shell" / "web"
    assert (web_dir / asset).is_file(), f"missing frontend asset: {asset}"


def test_frontend_resolves_through_importlib_resources() -> None:
    """The wheel must resolve assets without relying on __file__ or the source tree."""
    from importlib.resources import as_file, files

    with as_file(files("asoy.shell") / "web") as web_dir:
        assert (web_dir / "index.html").is_file()


def test_run_window_is_importable() -> None:
    assert callable(run_window)
