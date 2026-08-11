"""The classifier's measurement harness (ADR-026).

Two kinds of test live here, and keeping them apart matters.

The metric tests run everywhere and use synthetic results. They check that the harness counts what
it claims to count — a confusion matrix that is subtly wrong would let a real regression pass, and
nothing downstream would catch it.

The acceptance run is marked `reference` and is excluded from the default suite, because it makes
one real vision call per block. **It skips when the core set is empty, which it is today.** A
harness that reported success against no entries would be the worst possible outcome: a green
result standing in for a measurement nobody made.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from asoy.classifier import Classification, Evidence, PictureBlock, classify
from asoy.classifier.reference import (
    CORE_SET,
    MANIFEST_NAME,
    MANIFEST_VERSION,
    MAX_CROSS_FAMILY_RATE,
    MAX_UNKNOWN_RATE,
    Entry,
    Metrics,
    ReferenceError,
    evaluate,
    extension_directory,
    load_manifest,
)
from asoy.fences import DescriptionType
from asoy.tiers import Tier, detect

PHOTOGRAPH = DescriptionType.PHOTOGRAPH
ILLUSTRATION = DescriptionType.ILLUSTRATION
DIAGRAM = DescriptionType.DIAGRAM
CHART = DescriptionType.CHART
UNKNOWN = DescriptionType.UNKNOWN

REPO_ROOT = Path(__file__).resolve().parent.parent


def _metrics(*pairs: tuple[DescriptionType, DescriptionType]) -> Metrics:
    metrics = Metrics()
    for expected, predicted in pairs:
        metrics.record(expected, predicted)
    return metrics


# --- The metrics themselves ---------------------------------------------------------------------


def test_cross_family_counts_pictorial_against_graphical_both_ways() -> None:
    metrics = _metrics(
        (PHOTOGRAPH, CHART),
        (ILLUSTRATION, DIAGRAM),
        (CHART, PHOTOGRAPH),
        (DIAGRAM, ILLUSTRATION),
    )
    assert metrics.cross_family == 4
    assert metrics.cross_family_rate == 1.0


def test_within_family_confusion_is_not_counted_as_cross_family() -> None:
    """The distinction the bar rests on. Conflating them would cap the wrong thing."""
    metrics = _metrics((PHOTOGRAPH, ILLUSTRATION), (DIAGRAM, CHART))

    assert metrics.cross_family == 0
    assert metrics.within_family == 2


def test_a_correct_answer_is_neither_kind_of_confusion() -> None:
    metrics = _metrics((PHOTOGRAPH, PHOTOGRAPH), (CHART, CHART))
    assert (metrics.cross_family, metrics.within_family) == (0, 0)
    assert metrics.accuracy == 1.0


def test_unknown_is_not_cross_family_in_either_direction() -> None:
    """An abstention is not a wrong family. It is counted as an abstention and nothing else."""
    metrics = _metrics((PHOTOGRAPH, UNKNOWN), (UNKNOWN, CHART))

    assert metrics.cross_family == 0
    assert metrics.within_family == 0


def test_the_unknown_rate_counts_every_abstention_including_the_right_ones() -> None:
    """The reading the acceptance bar names, stated so the arithmetic is not a surprise."""
    metrics = _metrics(
        (UNKNOWN, UNKNOWN), (PHOTOGRAPH, UNKNOWN), (CHART, CHART), (DIAGRAM, DIAGRAM)
    )

    assert metrics.predicted_unknown == 2
    assert metrics.unknown_rate == 0.5
    assert metrics.expected_unknown == 1
    assert metrics.wrongly_unknown == 1, "the abstention that actually cost something"
    assert metrics.wrongly_unknown_rate == 0.25


def test_overconfident_counts_a_type_given_where_unknown_was_right() -> None:
    """ADR-026 keeps `unknown` rather than guessing. No other figure would show this failing."""
    metrics = _metrics((UNKNOWN, CHART), (UNKNOWN, UNKNOWN))
    assert metrics.overconfident == 1


def test_the_bar_is_never_met_by_an_empty_set() -> None:
    """A harness that passes on no evidence is worse than one that fails."""
    empty = Metrics()

    assert empty.total == 0
    assert empty.meets_bar is False
    assert "no entries" in empty.report("core")


def test_the_bar_is_met_only_when_both_capped_figures_are_within_it() -> None:
    clean = _metrics(*[(CHART, CHART)] * 20)
    assert clean.meets_bar is True

    too_much_cross = _metrics(*[(CHART, CHART)] * 18, (PHOTOGRAPH, CHART), (CHART, PHOTOGRAPH))
    assert too_much_cross.cross_family_rate > MAX_CROSS_FAMILY_RATE
    assert too_much_cross.meets_bar is False

    too_many_unknown = _metrics(*[(CHART, CHART)] * 14, *[(CHART, UNKNOWN)] * 6)
    assert too_many_unknown.unknown_rate > MAX_UNKNOWN_RATE
    assert too_many_unknown.meets_bar is False


def test_within_family_confusion_alone_does_not_fail_the_bar() -> None:
    """Recorded and uncapped for v1. Capping it is the reversal condition, not the default."""
    metrics = _metrics(*[(PHOTOGRAPH, ILLUSTRATION)] * 20)

    assert metrics.within_family == 20
    assert metrics.accuracy == 0.0
    assert metrics.meets_bar is True, "uncapped means uncapped, however uncomfortable it reads"


def test_the_confusion_table_names_every_type_on_both_axes() -> None:
    table = _metrics((PHOTOGRAPH, CHART)).confusion_table()
    for kind in DescriptionType:
        assert kind.value in table


def test_the_report_states_both_readings_of_the_unknown_rate() -> None:
    report = _metrics((UNKNOWN, UNKNOWN), (PHOTOGRAPH, UNKNOWN), (CHART, CHART)).report("core")

    assert "unknown" in report
    assert "wrongly unknown" in report
    assert "the right answer" in report


# --- The manifest -------------------------------------------------------------------------------


def _write(directory: Path, entries: list[dict], version: int = MANIFEST_VERSION) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / MANIFEST_NAME).write_text(
        json.dumps({"version": version, "entries": entries}), encoding="utf-8"
    )
    return directory


def _entry(**overrides) -> dict:
    return {
        "image": "images/one.png",
        "source": "a-book.epub",
        "locator": "picture[0]",
        "expected": "chart",
        "reasoning": "Plotted series against a labelled axis.",
        **overrides,
    }


def test_a_manifest_round_trips_into_entries(tmp_path: Path) -> None:
    directory = _write(tmp_path, [_entry(caption="Fig. 1.", context="Rainfall rose.")])
    (entry,) = load_manifest(directory)

    assert entry.expected is CHART
    assert entry.image == directory / "images/one.png"
    assert entry.source == "a-book.epub"
    assert entry.caption == "Fig. 1."
    assert entry.context == "Rainfall rose."
    assert entry.reasoning


def test_caption_and_context_default_to_empty(tmp_path: Path) -> None:
    (entry,) = load_manifest(_write(tmp_path, [_entry()]))
    assert (entry.caption, entry.context) == ("", "")


def test_an_absent_manifest_is_an_empty_set_not_an_error(tmp_path: Path) -> None:
    """The core is expected to be absent until the books are gathered."""
    assert load_manifest(tmp_path / "nothing-here") == ()


@pytest.mark.parametrize("missing", ["image", "source", "locator", "reasoning"])
def test_a_manifest_missing_a_required_field_is_refused(tmp_path: Path, missing: str) -> None:
    """A silently skipped entry would shrink the set and move the bar without saying so."""
    entry = _entry()
    del entry[missing]
    with pytest.raises(ReferenceError):
        load_manifest(_write(tmp_path, [entry]))


def test_an_empty_reasoning_is_refused(tmp_path: Path) -> None:
    """The line is what makes a disputed entry settleable without re-reading the book."""
    with pytest.raises(ReferenceError):
        load_manifest(_write(tmp_path, [_entry(reasoning="   ")]))


def test_an_unknown_expected_type_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ReferenceError):
        load_manifest(_write(tmp_path, [_entry(expected="sculpture")]))


def test_a_manifest_from_a_future_version_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ReferenceError):
        load_manifest(_write(tmp_path, [_entry()], version=MANIFEST_VERSION + 1))


def test_a_malformed_manifest_is_refused(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / MANIFEST_NAME).write_text("{not json", encoding="utf-8")
    with pytest.raises(ReferenceError):
        load_manifest(tmp_path)


def test_a_missing_image_is_reported_rather_than_scored(tmp_path: Path) -> None:
    """Scoring an entry whose image did not load would measure the harness, not the classifier."""
    entry = Entry(
        image=tmp_path / "absent.png",
        source="a-book.epub",
        locator="picture[0]",
        expected=CHART,
        reasoning="Plotted series.",
    )
    with pytest.raises(ReferenceError):
        entry.to_block()


# --- The committed core -------------------------------------------------------------------------


def test_the_committed_core_manifest_is_valid() -> None:
    """It is empty today, and it must still be a manifest this build can read."""
    entries = load_manifest(REPO_ROOT / CORE_SET)
    assert isinstance(entries, tuple)


def test_the_committed_core_has_an_image_for_every_entry() -> None:
    """Fails the moment the set lands with a manifest naming a file nobody committed."""
    for entry in load_manifest(REPO_ROOT / CORE_SET):
        assert entry.image.is_file(), f"{entry.locator} names a missing image: {entry.image}"


def test_evaluate_runs_the_classifier_over_every_entry(tmp_path: Path) -> None:
    """The harness itself, with a stand-in classifier and no model involved."""
    images = tmp_path / "images"
    images.mkdir(parents=True)
    (images / "one.png").write_bytes(b"not really a png")

    entries = load_manifest(_write(tmp_path, [_entry(), _entry(expected="photograph")]))
    seen: list[PictureBlock] = []

    def always_chart(block: PictureBlock) -> Classification:
        seen.append(block)
        return Classification(
            type=CHART, certainty=0.9, evidence=Evidence.MODEL, tier=Tier.GPU, model="stand-in"
        )

    metrics = evaluate(entries, always_chart)

    assert len(seen) == 2
    assert metrics.total == 2
    assert metrics.correct == 1
    assert metrics.cross_family == 1, "the photograph called a chart"


def test_the_extension_set_is_off_unless_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """It never sets the bar, so it must never be picked up by accident."""
    monkeypatch.delenv("ASOY_REFERENCE_EXTENSION", raising=False)
    assert extension_directory() is None

    monkeypatch.setenv("ASOY_REFERENCE_EXTENSION", "/somewhere/local")
    assert extension_directory() == Path("/somewhere/local")


def test_the_extension_set_is_not_committed() -> None:
    """Modern book pages in a public Apache 2.0 repository would be someone else's work."""
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "reference/local/" in ignored


# --- The acceptance run -------------------------------------------------------------------------


@pytest.mark.reference
def test_the_classifier_meets_the_acceptance_bar(capsys: pytest.CaptureFixture[str]) -> None:
    """The real measurement. Skips rather than passing when there is nothing to measure.

    Requires Ollama with the tier's model pulled, and makes one vision call per block, so it is
    excluded from the default suite. See RUNBOOK section 9.
    """
    entries = load_manifest(REPO_ROOT / CORE_SET)
    if not entries:
        pytest.skip(
            "The committed core set is empty: the books are still being gathered. Every "
            "acceptance number for the classifier is unmeasured until it lands, and reporting a "
            "pass here would stand in for a measurement nobody made. See reference/classifier/."
        )

    tier = detect().tier
    metrics = evaluate(entries, lambda block: classify(block, tier=tier))

    with capsys.disabled():
        print(f"\ntier: {tier.value}\n{metrics.report('core')}")

    assert metrics.cross_family_rate <= MAX_CROSS_FAMILY_RATE, metrics.confusion_table()
    assert metrics.unknown_rate <= MAX_UNKNOWN_RATE, metrics.confusion_table()


@pytest.mark.reference
def test_the_local_extension_is_reported_but_sets_no_bar(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Reported alongside the core, and asserted against nothing. Deliberately."""
    directory = extension_directory()
    if directory is None or not load_manifest(directory):
        pytest.skip("No local extension set is configured (ASOY_REFERENCE_EXTENSION).")

    tier = detect().tier
    metrics = evaluate(load_manifest(directory), lambda block: classify(block, tier=tier))

    with capsys.disabled():
        print(f"\ntier: {tier.value}\n{metrics.report('local extension')}")
