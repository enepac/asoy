"""The classifier's measurement harness (ADR-026, ADR-027, RUNBOOK section 9).

The reference set is the instrument that decides whether a change to this component is an
improvement. Without it, "it reads better to me" is the only available evidence, and CLAUDE.md
section 9 names that as a mistake to avoid by name.

Two sets, and the difference between them is the point:

* **The committed core**, at `reference/classifier/`. Public-domain material, in the repository,
  reviewable, and the only thing the acceptance bar is measured against. A bar that moves with
  material nobody else can see is not a bar.
* **A local extension**, at the path in `ASOY_REFERENCE_EXTENSION`. Modern books whose pages
  cannot be committed. Tracked by its own manifest, reported alongside the core, and never used
  to set or move the bar.

**The core's images do not exist yet.** The books are being gathered. Everything here runs, and
every acceptance number it produces is unmeasured until the set lands. `evaluate` on an empty set
returns an empty result rather than a passing one, and the acceptance test skips rather than
reporting a vacuous success.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from asoy.classifier import Classification, PictureBlock
from asoy.fences import DescriptionType

CORE_SET = Path("reference/classifier")
MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1

EXTENSION_ENV_VAR = "ASOY_REFERENCE_EXTENSION"

# The acceptance bar, measured on the committed core only (ADR-026, narrowed by ADR-027).
#
# Cross-family means a pictorial block called graphical or the reverse — a photograph called a
# chart. It is capped tightly because it is the failure that selects a wholly wrong description
# approach: a chart prompt applied to a photograph produces confident prose about axes that do
# not exist.
MAX_CROSS_FAMILY_RATE = 0.05

# Within-family confusion (photograph against illustration, diagram against chart) is recorded
# and uncapped for v1. Both members of a pair get broadly similar description treatment, so the
# cost of confusing them is real but much smaller. See ADR-026 for the reversal condition.

# Wrong abstentions: blocks whose expected answer was a real type and which came back `unknown`.
# Measured against the typed blocks only — roughly 50 of the core's 60 — not against the whole
# set. Above this, the model call is not earning its cost and the pre-pass should be doing more.
#
# The earlier form of this bar counted every abstention against the whole set at 25%. That reading
# spent about 17% of its own budget on the ten deliberately-ambiguous blocks whose correct answer
# is `unknown`, leaving roughly 8% for actual mistakes — it penalised the behaviour it was written
# to protect. The all-abstentions rate is still reported, as context rather than as a bar.
#
# 20% is a considered starting point and not a measured one, and it moves with CERTAINTY_FLOOR.
# See ADR-027, which is where this bar is decided; ADR-026 carries the one it narrowed.
MAX_WRONGLY_UNKNOWN_RATE = 0.20

# Which types are near-substitutes for each other. Confusion inside a family is a smaller error
# than confusion across one, and the bar treats them differently.
#
# `table` joins the graphical family with ADR-028, which re-admitted it as an answer. It belongs
# there on the merits — a table and a chart both present data, and confusing them costs about what
# confusing a diagram for a chart costs. It also has to belong somewhere: a type in no family is
# counted as neither kind of confusion, so a chart called a table would drop out of both figures
# and out of the capped bar, and ADR-028's own reversal condition asks exactly that question.
PICTORIAL = frozenset({DescriptionType.PHOTOGRAPH, DescriptionType.ILLUSTRATION})
GRAPHICAL = frozenset({DescriptionType.DIAGRAM, DescriptionType.CHART, DescriptionType.TABLE})


class ReferenceError(RuntimeError):
    """The reference set could not be read. Raised rather than measured against silently."""


@dataclass(frozen=True)
class Entry:
    """One reference block: the input, the expected answer, and why that answer is right."""

    image: Path
    source: str
    locator: str
    expected: DescriptionType
    reasoning: str
    caption: str = ""
    context: str = ""
    # True when the figure reads sideways on the page, as scanned landscape plates do. Recorded
    # rather than corrected (ADR-028): de-rotating would tidy the input to make the test easier,
    # and a classifier that only works on upright figures does not work on scanned books. The
    # flag lets the confusion matrix be read both ways, so a bar met only on upright figures is
    # visible as the narrower claim it is.
    rotated: bool = False

    def to_block(self) -> PictureBlock:
        try:
            image = self.image.read_bytes()
        except OSError as exc:
            raise ReferenceError(f"Could not read {self.image}: {exc}") from exc
        return PictureBlock(
            image=image, caption=self.caption, context=self.context, locator=self.locator
        )


def _family(kind: DescriptionType) -> frozenset[DescriptionType] | None:
    if kind in PICTORIAL:
        return PICTORIAL
    if kind in GRAPHICAL:
        return GRAPHICAL
    return None


@dataclass
class Metrics:
    """What one run of the reference set produced."""

    total: int = 0
    matrix: Counter[tuple[DescriptionType, DescriptionType]] = field(default_factory=Counter)

    @property
    def correct(self) -> int:
        return sum(count for (want, got), count in self.matrix.items() if want is got)

    @property
    def predicted_unknown(self) -> int:
        return sum(
            count for (_, got), count in self.matrix.items() if got is DescriptionType.UNKNOWN
        )

    @property
    def expected_unknown(self) -> int:
        return sum(
            count for (want, _), count in self.matrix.items() if want is DescriptionType.UNKNOWN
        )

    @property
    def cross_family(self) -> int:
        """A pictorial block called graphical, or the reverse. The failure that matters most."""
        return sum(
            count
            for (want, got), count in self.matrix.items()
            if _family(want) is not None
            and _family(got) is not None
            and _family(want) != _family(got)
        )

    @property
    def within_family(self) -> int:
        """Photograph against illustration, diagram against chart. Recorded, uncapped for v1."""
        return sum(
            count
            for (want, got), count in self.matrix.items()
            if want is not got and _family(want) is not None and _family(want) == _family(got)
        )

    @property
    def overconfident(self) -> int:
        """Blocks whose right answer was `unknown` and which were given a type anyway.

        ADR-026 keeps `unknown` rather than replacing it with a guess. This counts the times that
        rule did not hold, which no other figure here would show.
        """
        return sum(
            count
            for (want, got), count in self.matrix.items()
            if want is DescriptionType.UNKNOWN and got is not DescriptionType.UNKNOWN
        )

    def _rate(self, count: int) -> float:
        return count / self.total if self.total else 0.0

    @property
    def cross_family_rate(self) -> float:
        return self._rate(self.cross_family)

    @property
    def unknown_rate(self) -> float:
        """Every block answered `unknown`, including the ones where that is the right answer.

        Reported as context, and **not a bar**. A set holding ten legitimately-ambiguous blocks in
        sixty reads about 0.17 here before a single mistake, so capping this figure would charge
        the classifier for abstaining exactly where abstaining is correct.
        """
        return self._rate(self.predicted_unknown)

    @property
    def typed_total(self) -> int:
        """Blocks whose expected answer is a real type. The denominator the bar is measured on."""
        return self.total - self.expected_unknown

    @property
    def wrongly_unknown(self) -> int:
        """`unknown` given where a real type was expected. The abstentions that cost something."""
        return sum(
            count
            for (want, got), count in self.matrix.items()
            if got is DescriptionType.UNKNOWN and want is not DescriptionType.UNKNOWN
        )

    @property
    def wrongly_unknown_rate(self) -> float:
        """The capped figure. Against typed blocks only, so ambiguous ones cannot consume it."""
        return self.wrongly_unknown / self.typed_total if self.typed_total else 0.0

    @property
    def ambiguous_abstentions(self) -> int:
        """Ambiguous blocks the classifier correctly declined to type."""
        return self.expected_unknown - self.overconfident

    @property
    def ambiguous_abstention_rate(self) -> float:
        """How often the classifier abstained where abstaining was right.

        Recorded and uncapped: ten blocks cannot carry a threshold. It is read as a signal rather
        than a score — a low number here means the classifier is guessing on blocks that do not
        support a guess, which no other figure would reveal, since guessing right occasionally
        raises accuracy while being exactly the behaviour ADR-026 rejects.
        """
        return (
            self.ambiguous_abstentions / self.expected_unknown if self.expected_unknown else 0.0
        )

    @property
    def accuracy(self) -> float:
        return self._rate(self.correct)

    @property
    def meets_bar(self) -> bool:
        """Both capped figures within the bar. Never true on an empty set."""
        return (
            self.total > 0
            and self.cross_family_rate <= MAX_CROSS_FAMILY_RATE
            and self.wrongly_unknown_rate <= MAX_WRONGLY_UNKNOWN_RATE
        )

    def record(self, expected: DescriptionType, predicted: DescriptionType) -> None:
        self.total += 1
        self.matrix[(expected, predicted)] += 1

    def confusion_table(self) -> str:
        """The full matrix, expected down the side and predicted across."""
        kinds = list(DescriptionType)
        width = max(len(k.value) for k in kinds) + 2
        header = "expected \\ got".ljust(16) + "".join(k.value.rjust(width) for k in kinds)
        rows = [header]
        for want in kinds:
            cells = "".join(str(self.matrix[(want, got)]).rjust(width) for got in kinds)
            rows.append(want.value.ljust(16) + cells)
        return "\n".join(rows)

    def report(self, label: str) -> str:
        if not self.total:
            return f"{label}: no entries. Nothing was measured."
        return "\n".join(
            [
                f"{label}: {self.total} blocks, {self.accuracy:.1%} exact",
                f"  cross-family   {self.cross_family:>3}  "
                f"{self.cross_family_rate:.1%}  (bar: {MAX_CROSS_FAMILY_RATE:.0%})",
                f"  within-family  {self.within_family:>3}  "
                f"{self._rate(self.within_family):.1%}  (recorded, uncapped for v1)",
                f"  wrongly unknown{self.wrongly_unknown:>3}  "
                f"{self.wrongly_unknown_rate:.1%}  of {self.typed_total} typed blocks  "
                f"(bar: {MAX_WRONGLY_UNKNOWN_RATE:.0%})",
                f"  all unknown    {self.predicted_unknown:>3}  "
                f"{self.unknown_rate:.1%}  (context, not a bar; "
                f"{self.expected_unknown} of these are the right answer)",
                f"  abstained when ambiguous  {self.ambiguous_abstentions:>3}  "
                + (
                    f"{self.ambiguous_abstention_rate:.1%} of {self.expected_unknown}  "
                    "(recorded, uncapped; low means guessing)"
                    if self.expected_unknown
                    else "(no ambiguous blocks in this set)"
                ),
                f"  overconfident  {self.overconfident:>3}  "
                "(a type given where `unknown` was expected)",
                "",
                self.confusion_table(),
            ]
        )


def load_manifest(directory: Path) -> tuple[Entry, ...]:
    """Read one set's manifest. An absent directory is empty, not an error.

    The core set is expected to be absent until the books are gathered, and a harness that raises
    on that would have to be commented out rather than run.
    """
    manifest = directory / MANIFEST_NAME
    if not manifest.is_file():
        return ()

    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReferenceError(f"Could not read {manifest}: {exc}") from exc

    version = payload.get("version")
    if version != MANIFEST_VERSION:
        raise ReferenceError(
            f"{manifest} declares version {version!r}; this build reads {MANIFEST_VERSION}."
        )

    entries: list[Entry] = []
    for index, raw in enumerate(payload.get("entries", [])):
        try:
            expected = DescriptionType(raw["expected"])
        except (KeyError, ValueError) as exc:
            raise ReferenceError(f"{manifest} entry {index}: bad 'expected' ({exc}).") from None

        for required in ("image", "source", "locator", "reasoning"):
            if not str(raw.get(required, "")).strip():
                raise ReferenceError(f"{manifest} entry {index}: '{required}' is required.")

        entries.append(
            Entry(
                image=directory / str(raw["image"]),
                source=str(raw["source"]),
                locator=str(raw["locator"]),
                expected=expected,
                reasoning=str(raw["reasoning"]),
                caption=str(raw.get("caption", "")),
                context=str(raw.get("context", "")),
                rotated=bool(raw.get("rotated", False)),
            )
        )
    return tuple(entries)


def extension_directory() -> Path | None:
    """The local extension set, if one is configured. Never committed, never sets the bar."""
    configured = os.environ.get(EXTENSION_ENV_VAR)
    return Path(configured) if configured else None


def evaluate(entries: tuple[Entry, ...], classify_one) -> Metrics:
    """Run `classify_one` over every entry and record what came back.

    `classify_one` takes a PictureBlock and returns a Classification, so a caller measuring a
    change supplies its own without this module knowing about tiers or clients.
    """
    metrics = Metrics()
    for entry in entries:
        result: Classification = classify_one(entry.to_block())
        metrics.record(entry.expected, result.type)
    return metrics
