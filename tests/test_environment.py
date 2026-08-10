"""Environment check tests (ARCHITECTURE section 6, ADR-008, CLAUDE.md section 6).

The ollama client is mocked by substituting sys.modules["ollama"], so the suite needs no Ollama
installation, no running server, and no network. Nothing here makes a real request.
"""

from __future__ import annotations

import sys
import types

import pytest

from asoy.environment import (
    DEFAULT_HOST,
    HOST_ENV_VAR,
    MODEL_TAGS,
    REQUEST_TIMEOUT_SECONDS,
    EnvironmentCheck,
    EnvironmentStatus,
    check,
    resolve_host,
)
from asoy.tiers import Tier


class _ClientRecorder:
    """Captures the kwargs the client was constructed with, so they can be asserted on."""

    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}


def _fake_ollama(
    *,
    recorder: _ClientRecorder,
    models: list[str] | None = None,
    list_raises: BaseException | None = None,
    malformed: bool = False,
) -> types.ModuleType:
    """Build a stand-in ollama module exposing only Client and its list() method."""
    module = types.ModuleType("ollama")

    class Client:
        def __init__(self, **kwargs: object) -> None:
            recorder.kwargs = kwargs

        def list(self) -> object:
            if list_raises is not None:
                raise list_raises
            if malformed:
                return types.SimpleNamespace(unexpected="shape")
            entries = [types.SimpleNamespace(model=tag) for tag in (models or [])]
            return types.SimpleNamespace(models=entries)

    module.Client = Client  # type: ignore[attr-defined]
    return module


@pytest.fixture
def ollama(monkeypatch: pytest.MonkeyPatch):
    recorder = _ClientRecorder()

    def _install(**kwargs) -> _ClientRecorder:
        monkeypatch.setitem(sys.modules, "ollama", _fake_ollama(recorder=recorder, **kwargs))
        return recorder

    return _install


class _ConnectError(Exception):
    """Stands in for httpx.ConnectError, matched by name the way the real one is."""


class _ReadTimeout(Exception):
    """Stands in for httpx.ReadTimeout."""


def test_connection_refused_names_both_not_running_and_not_installed(ollama) -> None:
    """Over HTTP the two are indistinguishable, so the message must not assert one."""
    ollama(list_raises=_ConnectError("connection refused"))
    result = check(Tier.GPU)
    assert result.ok is False
    assert result.status is EnvironmentStatus.OLLAMA_UNREACHABLE
    assert "not running" in result.detail
    assert "not installed" in result.detail


def test_unreachable_remedy_is_actionable(ollama) -> None:
    ollama(list_raises=_ConnectError("connection refused"))
    result = check(Tier.GPU)
    assert "https://ollama.com/download" in result.remedy
    assert HOST_ENV_VAR in result.remedy


def test_timeout_returns_not_ok_rather_than_hanging(ollama) -> None:
    ollama(list_raises=_ReadTimeout("timed out"))
    result = check(Tier.CPU)
    assert result.ok is False
    assert result.status is EnvironmentStatus.OLLAMA_UNREACHABLE


def test_timeout_is_passed_to_the_client(ollama) -> None:
    """A hung startup is worse than a reported failure, so the bound must actually be applied."""
    recorder = ollama(models=[MODEL_TAGS[Tier.GPU]])
    check(Tier.GPU)
    assert recorder.kwargs["timeout"] == REQUEST_TIMEOUT_SECONDS


def test_host_is_passed_to_the_client(ollama) -> None:
    recorder = ollama(models=[MODEL_TAGS[Tier.GPU]])
    check(Tier.GPU)
    assert recorder.kwargs["host"] == DEFAULT_HOST


def test_model_present_returns_ok(ollama) -> None:
    ollama(models=[MODEL_TAGS[Tier.GPU], "some-other-model:7b"])
    result = check(Tier.GPU)
    assert result.ok is True
    assert result.status is EnvironmentStatus.READY
    assert result.remedy == ""


def test_model_absent_returns_the_pull_command_as_the_remedy(ollama) -> None:
    ollama(models=["some-other-model:7b"])
    result = check(Tier.GPU)
    assert result.ok is False
    assert result.status is EnvironmentStatus.MODEL_MISSING
    assert result.remedy == f"ollama pull {MODEL_TAGS[Tier.GPU]}"


@pytest.mark.parametrize("tier", [Tier.GPU, Tier.CPU])
def test_remedy_names_the_tag_for_the_tier_passed_in(ollama, tier: Tier) -> None:
    ollama(models=[])
    result = check(tier)
    assert MODEL_TAGS[tier] in result.remedy


def test_gpu_and_cpu_tiers_request_different_tags(ollama) -> None:
    """Guards the mapping: a single shared tag would silently give both tiers the same model."""
    assert MODEL_TAGS[Tier.GPU] != MODEL_TAGS[Tier.CPU]
    ollama(models=[MODEL_TAGS[Tier.GPU]])
    assert check(Tier.GPU).ok is True
    assert check(Tier.CPU).ok is False


def test_bare_model_name_matches_latest(ollama) -> None:
    """Ollama reports a bare name as ':latest'. Matching must not be naive string equality."""
    ollama(models=["moondream"])
    monkey_tag = MODEL_TAGS[Tier.CPU]
    result = check(Tier.CPU)
    # 'moondream' normalises to 'moondream:latest', which is not 'moondream:v2'.
    assert result.ok is False, f"{monkey_tag} must not match a different tag"


def test_malformed_response_returns_not_ok_rather_than_raising(ollama) -> None:
    ollama(malformed=True)
    result = check(Tier.GPU)
    assert result.ok is False
    assert result.status is EnvironmentStatus.CHECK_FAILED
    assert result.remedy


def test_unexpected_error_is_reported_as_check_failed(ollama) -> None:
    ollama(list_raises=ValueError("something odd"))
    result = check(Tier.GPU)
    assert result.ok is False
    assert result.status is EnvironmentStatus.CHECK_FAILED
    assert "something odd" in result.detail


def test_missing_ollama_library_returns_not_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "ollama":
            raise ImportError("No module named 'ollama'")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "ollama", raising=False)
    monkeypatch.setattr("builtins.__import__", fake_import)
    result = check(Tier.GPU)
    assert result.ok is False
    assert result.status is EnvironmentStatus.CHECK_FAILED


@pytest.mark.parametrize(
    "kwargs",
    [
        {"list_raises": _ConnectError("refused")},
        {"list_raises": _ReadTimeout("timed out")},
        {"list_raises": ValueError("odd")},
        {"list_raises": OSError("socket gone")},
        {"malformed": True},
        {"models": []},
        {"models": ["qwen3-vl:4b", "moondream:v2"]},
    ],
    ids=["connect", "timeout", "value-error", "os-error", "malformed", "empty", "present"],
)
@pytest.mark.parametrize("tier", [Tier.GPU, Tier.CPU])
def test_check_never_raises(ollama, kwargs, tier: Tier) -> None:
    ollama(**kwargs)
    result = check(tier)
    assert isinstance(result, EnvironmentCheck)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"list_raises": _ConnectError("refused")},
        {"list_raises": ValueError("odd")},
        {"malformed": True},
        {"models": []},
    ],
    ids=["connect", "value-error", "malformed", "empty"],
)
def test_every_failure_carries_a_remedy(ollama, kwargs) -> None:
    """CLAUDE.md section 6: user-facing messages are actionable, not merely accurate."""
    ollama(**kwargs)
    result = check(Tier.GPU)
    assert result.ok is False
    assert result.detail.strip()
    assert result.remedy.strip()


def test_host_defaults_when_env_var_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(HOST_ENV_VAR, raising=False)
    assert resolve_host() == DEFAULT_HOST


def test_host_comes_from_the_environment_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(HOST_ENV_VAR, "http://127.0.0.1:9999")
    assert resolve_host() == "http://127.0.0.1:9999"


def test_result_is_frozen(ollama) -> None:
    from dataclasses import FrozenInstanceError

    ollama(models=[])
    result = check(Tier.GPU)
    with pytest.raises(FrozenInstanceError):
        result.ok = True  # type: ignore[misc]


def test_no_user_facing_string_contains_an_em_dash(ollama) -> None:
    """Project constraint: newly authored user-facing prose uses hyphens, not em-dashes."""
    for kwargs in ({"list_raises": _ConnectError("x")}, {"models": []}, {"malformed": True}):
        ollama(**kwargs)
        result = check(Tier.GPU)
        assert "—" not in result.detail
        assert "—" not in result.remedy
