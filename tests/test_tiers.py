"""Tier detection tests (ARCHITECTURE section 5, CLAUDE.md invariant 8).

torch is mocked throughout by substituting sys.modules["torch"], so the suite runs on a machine
with no CUDA device, no GPU at all, or no torch installed. Nothing here touches real hardware.
"""

from __future__ import annotations

import sys
import types
from dataclasses import FrozenInstanceError

import pytest

from asoy.tiers import GPU_TIER_MIN_BYTES, Tier, TierDetection, detect

MIB = 1024**2
GIB = 1024**3

# The reference card: an RTX 3050 whose nominal capacity is 6144 MiB, which is exactly 6 GiB.
NOMINAL_6GB_BYTES = 6144 * MIB

# What torch actually reports for such a card, once the driver has taken its reservation.
# This figure is representative rather than measured: the development machine has the card but
# a CPU-only torch build, so no real total_memory reading was available. The important property
# is the one the threshold comment describes, that it sits BELOW a literal 6 GiB.
OBSERVED_6GB_BYTES = 6_219_104_256  # about 5.79 GiB

FOUR_GB_BYTES = 4 * GIB


def _fake_torch(
    *,
    available: bool = True,
    name: str = "NVIDIA GeForce RTX 3050",
    total_memory: int = OBSERVED_6GB_BYTES,
    available_raises: BaseException | None = None,
    properties_raises: BaseException | None = None,
) -> types.ModuleType:
    """Build a stand-in torch module exposing only what detect() touches."""
    module = types.ModuleType("torch")

    def is_available() -> bool:
        if available_raises is not None:
            raise available_raises
        return available

    def get_device_properties(index: int) -> types.SimpleNamespace:
        if properties_raises is not None:
            raise properties_raises
        return types.SimpleNamespace(name=name, total_memory=total_memory)

    module.cuda = types.SimpleNamespace(  # type: ignore[attr-defined]
        is_available=is_available,
        get_device_properties=get_device_properties,
    )
    return module


@pytest.fixture
def install_fake_torch(monkeypatch: pytest.MonkeyPatch):
    def _install(**kwargs) -> None:
        monkeypatch.setitem(sys.modules, "torch", _fake_torch(**kwargs))

    return _install


def test_no_cuda_device_returns_cpu_tier(install_fake_torch) -> None:
    install_fake_torch(available=False)
    result = detect()
    assert result.tier is Tier.CPU
    assert result.device_name is None
    assert result.total_vram_bytes is None


def test_detection_never_raises_when_the_cuda_check_explodes(install_fake_torch) -> None:
    """A crash here would take down startup. The correct degraded behaviour is the CPU tier."""
    install_fake_torch(available_raises=RuntimeError("CUDA driver exploded"))
    result = detect()
    assert result.tier is Tier.CPU
    assert "CUDA driver exploded" in result.reason
    assert "RuntimeError" in result.reason


def test_detection_never_raises_when_device_properties_explode(install_fake_torch) -> None:
    install_fake_torch(properties_raises=OSError("device query failed"))
    result = detect()
    assert result.tier is Tier.CPU
    assert "device query failed" in result.reason


def test_detection_never_raises_when_torch_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """torch is a hard dependency via Docling, but a broken install must not block startup."""
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    def fake_import(name, *args, **kwargs):
        if name == "torch":
            raise ImportError("No module named 'torch'")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "torch", raising=False)
    monkeypatch.setattr("builtins.__import__", fake_import)
    result = detect()
    assert result.tier is Tier.CPU
    assert "torch" in result.reason


@pytest.mark.parametrize(
    ("label", "total_memory"),
    [
        ("nominal 6144 MiB", NOMINAL_6GB_BYTES),
        ("observed, below a literal 6 GiB", OBSERVED_6GB_BYTES),
    ],
)
def test_six_gb_reference_card_is_gpu_tier_at_nominal_and_observed_capacity(
    install_fake_torch, label: str, total_memory: int
) -> None:
    """Regression guard for the threshold trap.

    ARCHITECTURE section 5 says "6 GB VRAM or more", but a 6 GB card reports less than 6 GiB
    to torch because the driver reserves memory first. If someone tightens GPU_TIER_MIN_BYTES
    to a round 6 * 1024**3, the observed case below fails and this test is what catches it.
    Without this guard the reference card would be silently demoted to the CPU tier, and the
    only symptom would be worse chart descriptions with no error anywhere.
    """
    install_fake_torch(total_memory=total_memory)
    result = detect()
    assert result.tier is Tier.GPU, f"{label} ({total_memory} bytes) must classify as GPU"
    assert result.total_vram_bytes == total_memory
    assert result.device_name == "NVIDIA GeForce RTX 3050"


def test_observed_reference_capacity_would_fail_a_literal_six_gib_threshold() -> None:
    """Pins the reason the threshold is 5.5 GiB, so the comment cannot drift from the code."""
    assert OBSERVED_6GB_BYTES < 6 * GIB
    assert OBSERVED_6GB_BYTES >= GPU_TIER_MIN_BYTES


def test_four_gb_device_is_cpu_tier(install_fake_torch) -> None:
    install_fake_torch(name="NVIDIA GeForce GTX 1650", total_memory=FOUR_GB_BYTES)
    result = detect()
    assert result.tier is Tier.CPU
    assert result.device_name == "NVIDIA GeForce GTX 1650"
    assert result.total_vram_bytes == FOUR_GB_BYTES


@pytest.mark.parametrize(
    "kwargs",
    [
        {"available": False},
        {"total_memory": OBSERVED_6GB_BYTES},
        {"total_memory": FOUR_GB_BYTES},
        {"available_raises": RuntimeError("boom")},
        {"properties_raises": OSError("boom")},
    ],
    ids=["no-cuda", "gpu-tier", "cpu-tier-small-card", "availability-raises", "properties-raise"],
)
def test_reason_is_non_empty_in_every_branch(install_fake_torch, kwargs) -> None:
    """Invariant 8: the tier must be explainable, not merely known."""
    install_fake_torch(**kwargs)
    result = detect()
    assert result.reason.strip(), "every branch must explain itself"


def test_detection_result_is_frozen(install_fake_torch) -> None:
    install_fake_torch()
    result = detect()
    with pytest.raises(FrozenInstanceError):
        result.tier = Tier.CPU  # type: ignore[misc]


def test_total_vram_gib_conversion(install_fake_torch) -> None:
    install_fake_torch(total_memory=NOMINAL_6GB_BYTES)
    result = detect()
    assert result.total_vram_gib == pytest.approx(6.0)


def test_total_vram_gib_is_none_without_a_device(install_fake_torch) -> None:
    install_fake_torch(available=False)
    assert detect().total_vram_gib is None


def test_tier_values_are_exactly_two() -> None:
    assert [t.value for t in Tier] == ["GPU", "CPU"]


def test_detection_returns_the_documented_type(install_fake_torch) -> None:
    install_fake_torch()
    assert isinstance(detect(), TierDetection)
