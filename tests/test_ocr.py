"""The OCR layer: weights as a prerequisite, the engine in use, and a real scanned page (ADR-029).

Three defects sat stacked on this route and none of them was visible from the test suite, because
every test converted an EPUB and the declarative formats never touch OCR. The last test in this
file is the one that would have caught all three: it converts an image-only PDF, which cannot
complete unless OpenCV is intact, the ONNX engine is present, and `torch.compile` is disabled.

The others are cheap and specific, and each names the defect it stands against. See INC-001,
INC-002, and INC-003.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from asoy.ocr import (
    FETCH_COMMAND,
    MODELS_ENV_VAR,
    REQUIRED_WEIGHTS,
    OcrWeightsMissing,
    disable_torch_compile,
    models_dir,
    ocr_options,
    status,
    verify,
)

# --- INC-001: the broken OpenCV install ---------------------------------------------------------


def test_cv2_is_a_real_module_not_an_empty_namespace() -> None:
    """INC-001. A bare `import cv2` succeeds on the broken install, so importing is not the test.

    opencv-python's wheel unpacked without `__init__.py` or its extension module, leaving a
    directory that imports as an empty namespace package. Every OCR path died on the first call.
    The version was never the problem, so a version bound would not have caught this.
    """
    import cv2

    assert cv2.__file__ is not None, "cv2 imported as a namespace package, not a real module"
    assert callable(getattr(cv2, "setNumThreads", None)), "cv2 is present but not functional"


# --- INC-003: the silent engine fallback --------------------------------------------------------


def test_onnxruntime_is_installed() -> None:
    """INC-003. Without it RapidOCR falls back to its torch engine and says so only in a log line.

    ADR-019 decided ONNX Runtime on both tiers. The fallback was an accident, not a decision, and
    it ran undetected because nothing asserted which engine was actually chosen.
    """
    import onnxruntime

    assert onnxruntime.__version__


@pytest.mark.parametrize("weight", [w for w in REQUIRED_WEIGHTS if w.filename.endswith(".onnx")])
def test_every_model_asoy_passes_is_an_onnx_model(weight) -> None:
    """The engine is selected by what it is handed, so this is the assertion that fixes it."""
    assert weight.url.endswith(".onnx")
    assert "/onnx/" in weight.url


def test_torch_compile_is_disabled() -> None:
    """INC-003's companion: TorchInductor needs a C++ compiler no user machine has."""
    import os

    disable_torch_compile()
    assert os.environ.get("TORCHDYNAMO_DISABLE") == "1"

    try:
        import torch._dynamo

        assert torch._dynamo.config.disable is True
    except ImportError:  # pragma: no cover - torch is a hard dependency
        pytest.skip("torch is not installed")


# --- INC-002: the silent download ---------------------------------------------------------------


def test_weights_live_outside_site_packages() -> None:
    """A packaged install is read-only, and RapidOCR's default is inside the package tree."""
    where = models_dir()
    parts = {part.lower() for part in where.parts}

    assert "site-packages" not in parts
    assert str(where)
    assert not str(where).lower().startswith(str(Path(sys.prefix)).lower() + "\\lib")


def test_the_models_directory_is_overridable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(MODELS_ENV_VAR, str(tmp_path / "elsewhere"))
    assert models_dir() == tmp_path / "elsewhere"


def test_absent_weights_are_reported_with_the_command_to_run(tmp_path: Path) -> None:
    """INC-002. The conversion fails with a remedy rather than quietly downloading 30 MB."""
    with pytest.raises(OcrWeightsMissing) as excinfo:
        ocr_options(tmp_path / "empty")

    assert FETCH_COMMAND in excinfo.value.remedy
    assert "does not download" in excinfo.value.remedy
    assert excinfo.value.detail


def test_status_names_what_is_missing_without_raising(tmp_path: Path) -> None:
    current = status(tmp_path / "empty")

    assert current.ready is False
    assert len(current.missing) == len(REQUIRED_WEIGHTS)
    assert current.present == ()


def test_status_sees_weights_that_are_present(tmp_path: Path) -> None:
    for weight in REQUIRED_WEIGHTS:
        (tmp_path / weight.filename).write_bytes(b"not really a model")

    current = status(tmp_path)
    assert current.ready is True
    assert current.missing == ()


def test_a_zero_byte_weight_is_not_counted_as_present(tmp_path: Path) -> None:
    """A half-written file would otherwise pass the check and fail the conversion."""
    for weight in REQUIRED_WEIGHTS:
        (tmp_path / weight.filename).write_bytes(b"")

    assert status(tmp_path).ready is False


def test_a_corrupted_weight_fails_verification(tmp_path: Path) -> None:
    for weight in REQUIRED_WEIGHTS:
        (tmp_path / weight.filename).write_bytes(b"wrong contents")

    problems = verify(tmp_path)
    assert problems, "a file that does not match its checksum must be reported"
    assert any("checksum" in problem for problem in problems)


def test_ocr_options_point_at_the_controlled_directory(tmp_path: Path) -> None:
    for weight in REQUIRED_WEIGHTS:
        (tmp_path / weight.filename).write_bytes(b"not really a model")

    options = ocr_options(tmp_path)
    for path in (
        options.det_model_path,
        options.cls_model_path,
        options.rec_model_path,
        options.rec_keys_path,
    ):
        assert Path(path).parent == tmp_path, "every path is given, so nothing is resolved"


def test_a_conversion_never_calls_the_downloader() -> None:
    """Invariant 1 and ARCHITECTURE section 9: the fetch is user-initiated and nothing else.

    A static check, because the runtime path is the one that must never reach it. The parser
    configures OCR; if it ever imports `fetch`, a conversion could download again.
    """
    import asoy.orchestrator
    import asoy.parser

    for module in (asoy.parser, asoy.orchestrator):
        source = Path(module.__file__).read_text(encoding="utf-8")
        for call in ("fetch(", "import fetch"):
            assert call not in source, f"{module.__name__} must not reach the downloader"


def test_only_the_fetch_command_reaches_the_network() -> None:
    """The one place in the package that opens a URL, asserted rather than assumed."""
    package = Path(__import__("asoy").__file__).parent
    openers = []
    for source in sorted(package.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        if "urlopen" in text or "urllib.request" in text:
            openers.append(source.name)

    assert openers == ["__init__.py"], f"unexpected network callers: {openers}"


# --- The guard that would have caught all three -------------------------------------------------


def _scanned_pdf(path: Path) -> Path:
    """An image-only PDF: a page with no text layer, so it can only be read by OCR."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1240, 500), "white")
    draw = ImageDraw.Draw(image)
    # Large enough for the detector to find. The default font renders at about 11px, which is
    # below what PP-OCR detects on a page-sized canvas, and produced an empty result.
    draw.text((60, 120), "SCANNED PAGE", fill="black", font=ImageFont.load_default(size=72))
    image.save(path, "PDF", resolution=150.0)
    return path


def test_a_scanned_pdf_converts_end_to_end(tmp_path: Path) -> None:
    """The guard that matters. Four books converted while every OCR route was dead.

    This cannot pass unless OpenCV is intact (INC-001), the weights are present and reachable
    without a download (INC-002), the ONNX engine is installed (INC-003), and `torch.compile` is
    disabled. It is slow because it runs the real layout and OCR models, and it is worth it: no
    cheaper test covers the interaction, which is what the three incidents had in common.
    """
    if not status().ready:
        pytest.skip(
            f"The OCR models are not present. Run '{FETCH_COMMAND}' to enable this test — it is "
            "the only one that exercises the OCR path end to end."
        )

    from asoy.orchestrator import convert

    result = convert(_scanned_pdf(tmp_path / "scan.pdf"), tmp_path / "out")
    text = result.artifacts.text_path.read_text(encoding="utf-8")

    assert "SCANNED" in text.upper(), f"OCR produced no recognisable text: {text[:200]!r}"
    assert result.artifacts.chapter_count >= 1
