"""OCR Layer: RapidOCR on both tiers, the tier selecting the backend (ARCHITECTURE section 4.5).

One engine across both tiers, so OCR output differs by speed rather than by model (ADR-019).
Tesseract and PaddleOCR were removed and must not come back without reopening that ADR.

This module owns three things a scanned input needs, all three settled by ADR-029:

**Where the weights live.** In a directory Asoy controls, never in `site-packages`, which is
read-only in a packaged install and is where RapidOCR would otherwise put them.

**That a conversion never downloads.** RapidOCR fetches missing weights on first use, which turned
"convert this book" into a silent 30 MB request to a third-party host — the exact shape
ARCHITECTURE section 9 says does not exist. Every model path is passed explicitly, so there is
nothing for it to resolve and nothing for it to fetch. Absent weights fail with a remedy naming
the command to run.

**That the weights are a checked prerequisite, not shipped.** Redistribution permission for the
PP-OCR weights is unestablished: RapidOCR names Baidu as the copyright holder and supplies no
terms for them. Unestablished is blocking under ADR-011 and CLAUDE.md section 11, so they are
fetched once by an explicit user command, in the manner ADR-008 uses for Ollama.

The download in `fetch` is the one place in this codebase that reaches a host other than the
version endpoint. It runs only when a user asks for it, never as a side effect of converting.
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

MODELS_ENV_VAR = "ASOY_OCR_MODELS"

# Under the user's local application data, alongside the job records and logs of ARCHITECTURE
# section 7. Deliberately outside the installation directory: a packaged install is read-only,
# and weights written next to the executable would fail on a locked-down machine.
_DEFAULT_SUBDIR = Path("Asoy") / "ocr-models"

# How long a single weight download may take before it is reported rather than waited on.
DOWNLOAD_TIMEOUT_SECONDS = 300.0

_SOURCE = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2"


@dataclass(frozen=True)
class Weight:
    """One file RapidOCR needs, and how to know it arrived intact."""

    role: str
    filename: str
    url: str
    sha256: str = ""


# The defaults RapidOCR's own config selects for the ONNX engine: PP-OCRv6 detection and
# recognition at the `small` size, PP-OCRv4 classification. Pinned here by name and checksum so
# that an upstream retag cannot change what Asoy runs without the checksum failing first — the
# same reasoning ADR-019 applies to model tags.
REQUIRED_WEIGHTS: tuple[Weight, ...] = (
    Weight(
        role="detection",
        filename="PP-OCRv6_det_small.onnx",
        url=f"{_SOURCE}/onnx/PP-OCRv6/det/PP-OCRv6_det_small.onnx",
        sha256="090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f",
    ),
    Weight(
        role="classification",
        filename="ch_ppocr_mobile_v2.0_cls_mobile.onnx",
        url=f"{_SOURCE}/onnx/PP-OCRv4/cls/ch_ppocr_mobile_v2.0_cls_mobile.onnx",
        sha256="e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
    ),
    Weight(
        role="recognition",
        filename="PP-OCRv6_rec_small.onnx",
        url=f"{_SOURCE}/onnx/PP-OCRv6/rec/PP-OCRv6_rec_small.onnx",
        sha256="6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884",
    ),
    Weight(
        role="character dictionary",
        filename="ppocrv6_dict.txt",
        url=f"{_SOURCE}/paddle/PP-OCRv6/rec/PP-OCRv6_rec_small/ppocrv6_dict.txt",
    ),
)

FETCH_COMMAND = "asoy fetch-ocr-models"


class OcrWeightsMissing(RuntimeError):
    """The OCR weights are not present. Raised instead of downloading them."""

    def __init__(self, detail: str, remedy: str) -> None:
        super().__init__(f"{detail} {remedy}")
        self.detail = detail
        self.remedy = remedy


@dataclass(frozen=True)
class WeightsStatus:
    """Which weights are present, for the environment check and for the error path."""

    directory: Path
    present: tuple[Weight, ...]
    missing: tuple[Weight, ...]

    @property
    def ready(self) -> bool:
        return not self.missing


def models_dir() -> Path:
    """Where Asoy keeps the OCR weights. Overridable, and never inside the installation."""
    configured = os.environ.get(MODELS_ENV_VAR)
    if configured:
        return Path(configured)

    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / _DEFAULT_SUBDIR


def status(directory: Path | None = None) -> WeightsStatus:
    """Check which weights are on disk. Never raises, never downloads."""
    where = directory or models_dir()
    present, missing = [], []
    for weight in REQUIRED_WEIGHTS:
        target = where / weight.filename
        try:
            ok = target.is_file() and target.stat().st_size > 0
        except OSError:
            ok = False
        (present if ok else missing).append(weight)
    return WeightsStatus(directory=where, present=tuple(present), missing=tuple(missing))


def _missing_error(current: WeightsStatus) -> OcrWeightsMissing:
    names = ", ".join(w.role for w in current.missing)
    return OcrWeightsMissing(
        f"Scanned input needs the OCR models, and {len(current.missing)} of "
        f"{len(REQUIRED_WEIGHTS)} are not in {current.directory} ({names}).",
        f"Run '{FETCH_COMMAND}' once to download them, then convert again. Asoy does not "
        "download them during a conversion, so that converting a book never reaches the network.",
    )


def ocr_options(directory: Path | None = None):
    """Docling's OCR options with every model path given explicitly.

    Passing all four paths is what makes the download impossible rather than merely unlikely:
    RapidOCR resolves and fetches only what it was not given.
    """
    from docling.datamodel.pipeline_options import RapidOcrOptions

    current = status(directory)
    if not current.ready:
        raise _missing_error(current)

    where = current.directory
    return RapidOcrOptions(
        det_model_path=str(where / "PP-OCRv6_det_small.onnx"),
        cls_model_path=str(where / "ch_ppocr_mobile_v2.0_cls_mobile.onnx"),
        rec_model_path=str(where / "PP-OCRv6_rec_small.onnx"),
        rec_keys_path=str(where / "ppocrv6_dict.txt"),
    )


def disable_torch_compile() -> None:
    """Stop PyTorch from JIT-compiling Docling's layout model (ADR-029).

    TorchInductor shells out to a C++ compiler, and `cl.exe` is absent on essentially every
    Windows machine that has not installed Visual Studio. Without this, every scanned PDF fails
    with `InvalidCxxCompiler`, which reads as a broken product rather than a missing toolchain.

    Set in-process rather than asking the user for an environment variable: a documented
    workaround that every user must apply is not a fix.
    """
    os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
    try:
        import torch._dynamo

        torch._dynamo.config.disable = True
    except Exception:
        # Torch absent or restructured. The environment variable above is set either way, and it
        # is read at import time by every torch version that has Dynamo at all.
        pass


def _digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


def verify(directory: Path | None = None) -> list[str]:
    """Check the checksums of what is on disk. Returns a list of problems, empty when sound."""
    where = directory or models_dir()
    problems: list[str] = []
    for weight in REQUIRED_WEIGHTS:
        target = where / weight.filename
        if not weight.sha256 or not target.is_file():
            continue
        actual = _digest(target)
        if actual != weight.sha256:
            problems.append(
                f"{weight.filename} does not match its recorded checksum "
                f"(expected {weight.sha256[:16]}…, found {actual[:16]}…)."
            )
    return problems


def fetch(directory: Path | None = None, *, report=print) -> WeightsStatus:
    """Download the OCR weights. **User-initiated only** — never called by a conversion.

    This is the one place Asoy contacts a host other than the version endpoint, and it exists
    because the weights cannot be redistributed (ADR-029). It is reached from `asoy
    fetch-ocr-models` and from nowhere else.
    """
    where = directory or models_dir()
    where.mkdir(parents=True, exist_ok=True)

    for weight in REQUIRED_WEIGHTS:
        target = where / weight.filename
        if target.is_file() and target.stat().st_size > 0:
            report(f"  present  {weight.filename}")
            continue

        report(f"  fetching {weight.filename} ({weight.role})")
        partial = target.with_suffix(target.suffix + ".partial")
        try:
            with urllib.request.urlopen(  # noqa: S310 - a pinned https URL, not user input
                weight.url, timeout=DOWNLOAD_TIMEOUT_SECONDS
            ) as response, partial.open("wb") as out:
                while chunk := response.read(1 << 20):
                    out.write(chunk)
        except Exception as exc:
            partial.unlink(missing_ok=True)
            raise OcrWeightsMissing(
                f"Could not download {weight.filename} ({type(exc).__name__}: {exc}).",
                "Check the connection and run the command again. Nothing was left half-written.",
            ) from exc

        if weight.sha256:
            actual = _digest(partial)
            if actual != weight.sha256:
                partial.unlink(missing_ok=True)
                raise OcrWeightsMissing(
                    f"{weight.filename} downloaded but its checksum does not match "
                    f"(expected {weight.sha256[:16]}…, found {actual[:16]}…).",
                    "The file was discarded rather than used. Run the command again.",
                )
        partial.replace(target)

    return status(where)
