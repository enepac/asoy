"""Smoke tests: the package imports, the skeleton is intact, and the entry point runs.

These guard the scaffold itself. They catch a component package being renamed or dropped
without ARCHITECTURE section 4 being updated alongside it, and a frontend asset going
missing from the wheel.
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


def test_main_reports_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main() == 0
    assert capsys.readouterr().out.strip() == f"asoy {version('asoy')}"


def test_module_entry_point_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "asoy"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("asoy ")


@pytest.mark.parametrize("asset", WEB_ASSETS)
def test_frontend_asset_present(asset: str) -> None:
    web_dir = Path(asoy.__file__).parent / "shell" / "web"
    assert (web_dir / asset).is_file(), f"missing frontend asset: {asset}"
