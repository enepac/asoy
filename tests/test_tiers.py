"""Tier detection tests (ARCHITECTURE section 5, ADR-021, CLAUDE.md invariant 8).

NVML is mocked throughout by substituting sys.modules["pynvml"], so the suite runs on a machine
with no NVIDIA GPU, no driver, and no binding installed. Nothing here touches real hardware.
"""

from __future__ import annotations

import sys
import types
from dataclasses import FrozenInstanceError

import pytest

from asoy.tiers import GPU_TIER_MIN_BYTES, Tier, TierDetection, detect

MIB = 1024**2
GIB = 1024**3

# The reference card: an RTX 3050 with a nominal 6144 MiB, which is exactly 6 GiB. NVML on the
# development machine reports this figure exactly, measured.
NOMINAL_6GB_BYTES = 6144 * MIB

# A card marketed as "6 GB" in decimal units is 6,000,000,000 bytes, which is only 5.59 GiB.
# It must still reach the GPU tier. This is the case a literal 6 GiB threshold would break.
DECIMAL_6GB_BYTES = 6_000_000_000

FOUR_GB_BYTES = 4 * GIB


class _ShutdownRecorder:
    """Tracks whether nvmlShutdown ran, so the finally block can be asserted on."""

    def __init__(self) -> None:
        self.init_calls = 0
        self.shutdown_calls = 0


def _fake_pynvml(
    *,
    recorder: _ShutdownRecorder,
    device_count: int = 1,
    name: object = "NVIDIA GeForce RTX 3050",
    total_memory: int = NOMINAL_6GB_BYTES,
    init_raises: BaseException | None = None,
    count_raises: BaseException | None = None,
    memory_raises: BaseException | None = None,
    shutdown_raises: BaseException | None = None,
) -> types.ModuleType:
    """Build a stand-in pynvml module exposing only what detect() touches."""
    module = types.ModuleType("pynvml")

    def nvmlInit() -> None:
        recorder.init_calls += 1
        if init_raises is not None:
            raise init_raises

    def nvmlShutdown() -> None:
        recorder.shutdown_calls += 1
        if shutdown_raises is not None:
            raise shutdown_raises

    def nvmlDeviceGetCount() -> int:
        if count_raises is not None:
            raise count_raises
        return device_count

    def nvmlDeviceGetHandleByIndex(index: int) -> object:
        return object()

    def nvmlDeviceGetName(handle: object) -> object:
        return name

    def nvmlDeviceGetMemoryInfo(handle: object) -> types.SimpleNamespace:
        if memory_raises is not None:
            raise memory_raises
        return types.SimpleNamespace(total=total_memory, free=0, used=0)

    module.nvmlInit = nvmlInit  # type: ignore[attr-defined]
    module.nvmlShutdown = nvmlShutdown  # type: ignore[attr-defined]
    module.nvmlDeviceGetCount = nvmlDeviceGetCount  # type: ignore[attr-defined]
    module.nvmlDeviceGetHandleByIndex = nvmlDeviceGetHandleByIndex  # type: ignore[attr-defined]
    module.nvmlDeviceGetName = nvmlDeviceGetName  # type: ignore[attr-defined]
    module.nvmlDeviceGetMemoryInfo = nvmlDeviceGetMemoryInfo  # type: ignore[attr-defined]
    return module


@pytest.fixture
def nvml(monkeypatch: pytest.MonkeyPatch):
    """Install a fake pynvml and hand back the recorder for shutdown assertions."""
    recorder = _ShutdownRecorder()

    def _install(**kwargs) -> _ShutdownRecorder:
        monkeypatch.setitem(sys.modules, "pynvml", _fake_pynvml(recorder=recorder, **kwargs))
        return recorder

    return _install


def test_no_driver_returns_cpu_tier(nvml) -> None:
    nvml(init_raises=RuntimeError("NVML Shared Library Not Found"))
    result = detect()
    assert result.tier is Tier.CPU
    assert result.device_name is None
    assert "NVML Shared Library Not Found" in result.reason


def test_zero_devices_returns_cpu_tier(nvml) -> None:
    nvml(device_count=0)
    result = detect()
    assert result.tier is Tier.CPU
    assert result.device_name is None
    assert result.total_vram_bytes is None


def test_detection_never_raises_when_device_count_explodes(nvml) -> None:
    """A crash here would take down startup. The correct degraded behaviour is the CPU tier."""
    nvml(count_raises=RuntimeError("device enumeration failed"))
    result = detect()
    assert result.tier is Tier.CPU
    assert "device enumeration failed" in result.reason
    assert "RuntimeError" in result.reason


def test_detection_never_raises_when_memory_query_explodes(nvml) -> None:
    nvml(memory_raises=OSError("memory info unavailable"))
    result = detect()
    assert result.tier is Tier.CPU
    assert "memory info unavailable" in result.reason


def test_detection_never_raises_when_the_binding_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """nvidia-ml-py is a declared dependency, but a broken install must not block startup."""
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "pynvml":
            raise ImportError("No module named 'pynvml'")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "pynvml", raising=False)
    monkeypatch.setattr("builtins.__import__", fake_import)
    result = detect()
    assert result.tier is Tier.CPU
    assert "NVML" in result.reason


def test_nvml_is_shut_down_even_when_a_later_step_raises(nvml) -> None:
    """Leaking an NVML handle on every failed detection would be a slow resource bug."""
    recorder = nvml(count_raises=RuntimeError("boom"))
    detect()
    assert recorder.init_calls == 1
    assert recorder.shutdown_calls == 1


def test_nvml_is_shut_down_on_the_success_path(nvml) -> None:
    recorder = nvml()
    detect()
    assert recorder.shutdown_calls == 1


def test_a_failing_shutdown_does_not_break_detection(nvml) -> None:
    nvml(shutdown_raises=RuntimeError("shutdown failed"))
    result = detect()
    assert result.tier is Tier.GPU


def test_shutdown_is_not_called_when_init_failed(nvml) -> None:
    """Nothing was acquired, so nothing should be released."""
    recorder = nvml(init_raises=RuntimeError("no driver"))
    detect()
    assert recorder.shutdown_calls == 0


@pytest.mark.parametrize(
    ("label", "total_memory"),
    [
        ("nominal 6144 MiB, measured on the reference card", NOMINAL_6GB_BYTES),
        ("6 GB marketed in decimal units, only 5.59 GiB", DECIMAL_6GB_BYTES),
    ],
)
def test_six_gb_reference_card_is_gpu_tier_at_nominal_and_reduced_capacity(
    nvml, label: str, total_memory: int
) -> None:
    """Regression guard for the threshold trap.

    ARCHITECTURE section 5 says "6 GB VRAM or more", but a 6 GB card does not necessarily report
    6 GiB: decimal marketing makes "6 GB" 5.59 GiB, and driver or ECC reservation can shave more.
    If someone tightens GPU_TIER_MIN_BYTES to a round 6 * 1024**3, the decimal case below fails
    and this test is what catches it. Without this guard such a card would be silently demoted to
    the CPU tier, and the only symptom would be worse chart descriptions with no error anywhere.
    """
    nvml(total_memory=total_memory)
    result = detect()
    assert result.tier is Tier.GPU, f"{label} ({total_memory} bytes) must classify as GPU"
    assert result.total_vram_bytes == total_memory
    assert result.device_name == "NVIDIA GeForce RTX 3050"


def test_decimal_six_gb_would_fail_a_literal_six_gib_threshold() -> None:
    """Pins the reason the threshold is 5.5 GiB, so the comment cannot drift from the code."""
    assert DECIMAL_6GB_BYTES < 6 * GIB
    assert DECIMAL_6GB_BYTES >= GPU_TIER_MIN_BYTES


def test_four_gb_device_is_cpu_tier(nvml) -> None:
    nvml(name="NVIDIA GeForce GTX 1650", total_memory=FOUR_GB_BYTES)
    result = detect()
    assert result.tier is Tier.CPU
    assert result.device_name == "NVIDIA GeForce GTX 1650"
    assert result.total_vram_bytes == FOUR_GB_BYTES


def test_device_name_accepts_bytes_from_older_bindings(nvml) -> None:
    nvml(name=b"NVIDIA GeForce RTX 3050")
    assert detect().device_name == "NVIDIA GeForce RTX 3050"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"init_raises": RuntimeError("no driver")},
        {"device_count": 0},
        {"total_memory": NOMINAL_6GB_BYTES},
        {"total_memory": FOUR_GB_BYTES},
        {"count_raises": RuntimeError("boom")},
        {"memory_raises": OSError("boom")},
    ],
    ids=["no-driver", "zero-devices", "gpu-tier", "cpu-tier-small-card", "count-raises",
         "memory-raises"],
)
def test_reason_is_non_empty_in_every_branch(nvml, kwargs) -> None:
    """Invariant 8: the tier must be explainable, not merely known."""
    nvml(**kwargs)
    result = detect()
    assert result.reason.strip(), "every branch must explain itself"


def test_cpu_reason_no_longer_mentions_torch(nvml) -> None:
    """ADR-021: the old reason blamed torch, which was misleading. It must not come back."""
    nvml(init_raises=RuntimeError("no driver"))
    assert "torch" not in detect().reason.lower()


def test_detection_result_is_frozen(nvml) -> None:
    nvml()
    result = detect()
    with pytest.raises(FrozenInstanceError):
        result.tier = Tier.CPU  # type: ignore[misc]


def test_total_vram_gib_conversion(nvml) -> None:
    nvml(total_memory=NOMINAL_6GB_BYTES)
    assert detect().total_vram_gib == pytest.approx(6.0)


def test_total_vram_gib_is_none_without_a_device(nvml) -> None:
    nvml(device_count=0)
    assert detect().total_vram_gib is None


def test_tier_values_are_exactly_two() -> None:
    assert [t.value for t in Tier] == ["GPU", "CPU"]


def test_detection_returns_the_documented_type(nvml) -> None:
    nvml()
    assert isinstance(detect(), TierDetection)
