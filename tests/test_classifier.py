"""Block classifier: the pre-pass, the model call, and the abstention rule (ADR-026).

No test here reaches Ollama. The vision call is exercised through a stand-in client, which is
what makes the failure paths testable at all — a real model cannot be made to time out, return
an off-schema reply, or report a certainty of 0.31 on demand.

The behaviour these guard is the one ADR-026 settled and that a later session would most plausibly
"improve": that a low-certainty answer is discarded rather than used. Replacing an `unknown` with
the model's best guess would raise every accuracy number on the reference set while making the
product worse, because the wrong type selects the wrong description prompt.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from asoy.classifier import (
    CAPTION_CERTAINTY,
    CERTAINTY_FLOOR,
    MODEL_CERTAINTY_CEILING,
    Classification,
    Evidence,
    PictureBlock,
    classify,
    classify_all,
)
from asoy.classifier.prepass import TERMS, read_caption
from asoy.classifier.prompt import (
    CLASSIFIABLE_TYPES,
    CLASSIFICATION_PROMPT,
    RESPONSE_SCHEMA,
    build_prompt,
)
from asoy.environment import model_tag_for
from asoy.fences import DescriptionType
from asoy.tiers import Tier

IMAGE = b"\x89PNG\r\n\x1a\n not really a png"


@dataclass
class FakeResponse:
    response: str


class FakeClient:
    """Stands in for ollama.Client. Records what it was asked, answers what it was told to."""

    def __init__(self, payload: object | str | None = None, raises: Exception | None = None):
        self.payload = payload
        self.raises = raises
        self.calls: list[dict[str, Any]] = []

    def generate(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        body = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return FakeResponse(response=body)


def _answer(kind: str, certainty: float) -> FakeClient:
    return FakeClient({"type": kind, "certainty": certainty})


def _block(**overrides: Any) -> PictureBlock:
    return PictureBlock(**{"image": IMAGE, "locator": "picture[0]", **overrides})


# --- The caption pre-pass -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("caption", "expected"),
    [
        ("Fig. 3. Photograph of the north face.", DescriptionType.PHOTOGRAPH),
        ("Plate IV.—An engraving after Turner.", DescriptionType.ILLUSTRATION),
        ("Diagram of the escapement.", DescriptionType.DIAGRAM),
        ("Chart showing rainfall by month.", DescriptionType.CHART),
        ("A map of the northern approaches", DescriptionType.DIAGRAM),
        ("PHOTOGRAPHS OF THE EXPEDITION", DescriptionType.PHOTOGRAPH),
    ],
)
def test_an_unambiguous_caption_settles_the_block(caption: str, expected: DescriptionType) -> None:
    client = _answer("chart", 0.99)
    result = classify(_block(caption=caption), tier=Tier.GPU, client=client)

    assert result.type is expected
    assert result.evidence is Evidence.CAPTION
    assert result.certainty == CAPTION_CERTAINTY
    assert client.calls == [], "the model must not be called for a caption that already answered"


@pytest.mark.parametrize(
    "caption",
    [
        "",
        "Fig. 12.",
        "Plate IV",
        "The north face at dawn",
        "Exhibit B",
        "A diagram after a photograph by Nadar",
        "Chart and illustration of the same voyage",
    ],
)
def test_an_unhelpful_caption_abstains(caption: str) -> None:
    """Zero families named, or two. Either way the caption is not evidence."""
    assert read_caption(caption).settled is False


def test_abstention_sends_the_block_to_the_model() -> None:
    client = _answer("diagram", 0.9)
    result = classify(_block(caption="Fig. 12."), tier=Tier.GPU, client=client)

    assert result.type is DescriptionType.DIAGRAM
    assert result.evidence is Evidence.MODEL
    assert len(client.calls) == 1


def test_the_pre_pass_terms_do_not_overlap_between_families() -> None:
    """A term in two families would make the answer depend on dictionary order."""
    seen: set[str] = set()
    for terms in TERMS.values():
        assert not (seen & terms), f"term appears in two families: {seen & terms}"
        seen |= terms


def test_generic_figure_words_are_not_terms() -> None:
    """`figure`, `plate`, `image` precede all four families and must settle nothing."""
    everything = {term for terms in TERMS.values() for term in terms}
    for generic in ("figure", "fig", "plate", "image", "picture", "exhibit", "illus"):
        assert generic not in everything


# --- The abstention rule ------------------------------------------------------------------------


def test_an_answer_below_the_floor_is_discarded() -> None:
    """ADR-026: `unknown` is never replaced by a guess.

    Using the answer anyway would raise the reference set's accuracy and make the product worse,
    because a wrong type selects a wrong description prompt and produces confident prose about
    the wrong kind of thing.
    """
    client = _answer("chart", CERTAINTY_FLOOR - 0.01)
    result = classify(_block(), tier=Tier.GPU, client=client)

    assert result.type is DescriptionType.UNKNOWN
    assert result.certainty == 0.0
    assert "below the" in result.detail
    assert "chart" in result.detail, "the discarded answer is still recorded"


def test_an_answer_at_the_floor_is_kept() -> None:
    result = classify(_block(), tier=Tier.GPU, client=_answer("chart", CERTAINTY_FLOOR))
    assert result.type is DescriptionType.CHART


def test_the_model_answering_unknown_is_respected() -> None:
    result = classify(_block(), tier=Tier.GPU, client=_answer("unknown", 0.99))
    assert result.type is DescriptionType.UNKNOWN
    assert result.evidence is Evidence.MODEL


def test_model_certainty_is_clamped_below_what_a_caption_earns() -> None:
    """A caption is a fact about the book. A model's opinion of itself is not calibrated."""
    result = classify(_block(), tier=Tier.GPU, client=_answer("chart", 1.0))
    assert result.certainty == MODEL_CERTAINTY_CEILING
    assert result.certainty < CAPTION_CERTAINTY


def test_certainty_is_on_the_scale_the_description_fence_uses() -> None:
    """Blast radius: this number feeds the fence's `confidence` attribute (ARCHITECTURE 4.8)."""
    from asoy.fences import format_confidence

    for certainty in (0.0, CERTAINTY_FLOOR, CAPTION_CERTAINTY, MODEL_CERTAINTY_CEILING):
        assert 0.0 <= certainty <= 1.0
        assert format_confidence(certainty)


# --- Failure paths ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "failure",
    [
        FakeClient(raises=ConnectionError("Ollama is not running")),
        FakeClient(raises=TimeoutError("took too long")),
        FakeClient(payload="not json at all"),
        FakeClient(payload={"type": "sculpture", "certainty": 0.9}),
        FakeClient(payload={"certainty": 0.9}),
    ],
)
def test_a_failed_call_yields_unknown_rather_than_raising(failure: FakeClient) -> None:
    """A classification failure must not cost the book, and must not be silent either."""
    result = classify(_block(), tier=Tier.GPU, client=failure)

    assert result.type is DescriptionType.UNKNOWN
    assert result.evidence is Evidence.NONE
    assert result.detail, "the failure is recorded even though the job continues"


def test_a_missing_certainty_does_not_become_a_confident_answer() -> None:
    result = classify(_block(), tier=Tier.GPU, client=FakeClient({"type": "chart"}))
    assert result.type is DescriptionType.UNKNOWN


def test_a_non_numeric_certainty_does_not_become_a_confident_answer() -> None:
    client = FakeClient({"type": "chart", "certainty": "very"})
    assert classify(_block(), tier=Tier.GPU, client=client).type is DescriptionType.UNKNOWN


# --- Invariant 8: the tier is recoverable -------------------------------------------------------


@pytest.mark.parametrize("tier", list(Tier))
def test_every_result_records_the_tier_and_model_it_ran_under(tier: Tier) -> None:
    """Invariant 8. The tier selects the model, so it selects the answer."""
    result = classify(_block(), tier=tier, client=_answer("chart", 0.9))

    assert result.tier is tier
    assert result.model == model_tag_for(tier)


def test_the_tier_is_recorded_even_when_the_caption_settled_it() -> None:
    result = classify(_block(caption="A chart of rainfall"), tier=Tier.CPU, client=FakeClient())
    assert result.tier is Tier.CPU
    assert result.model == model_tag_for(Tier.CPU)


def test_the_tier_is_recorded_on_a_failed_call() -> None:
    client = FakeClient(raises=ConnectionError("down"))
    assert classify(_block(), tier=Tier.CPU, client=client).tier is Tier.CPU


# --- What is sent -------------------------------------------------------------------------------


def test_the_call_carries_the_image_the_schema_and_the_tier_model() -> None:
    client = _answer("chart", 0.9)
    classify(_block(caption="Fig. 2.", context="Rainfall rose."), tier=Tier.GPU, client=client)

    call = client.calls[0]
    assert call["images"] == [IMAGE]
    assert call["format"] == RESPONSE_SCHEMA
    assert call["model"] == model_tag_for(Tier.GPU)


def test_the_prompt_carries_the_caption_and_context_but_not_the_pre_passs_conclusion() -> None:
    """Independence: the model is given the text, never the pre-pass's reading of it."""
    client = _answer("chart", 0.9)
    classify(
        _block(caption="Fig. 2. After Nadar.", context="Rainfall rose."),
        tier=Tier.GPU,
        client=client,
    )

    prompt = client.calls[0]["prompt"]
    assert "Fig. 2. After Nadar." in prompt
    assert "Rainfall rose." in prompt
    for verdict in ("pre-pass", "the caption suggests", "likely type"):
        assert verdict not in prompt


def test_a_block_with_no_text_gets_the_bare_prompt() -> None:
    assert build_prompt() == CLASSIFICATION_PROMPT
    assert build_prompt("  ", "") == CLASSIFICATION_PROMPT


def test_the_schema_offers_every_type_including_table() -> None:
    """ADR-028 re-admitted `table`. A scanned table is a picture and needs the right prompt."""
    allowed = set(RESPONSE_SCHEMA["properties"]["type"]["enum"])  # type: ignore[index]

    assert allowed == {kind.value for kind in DescriptionType}
    assert set(CLASSIFIABLE_TYPES) == set(DescriptionType)
    assert DescriptionType.TABLE in CLASSIFIABLE_TYPES


def test_a_scanned_table_can_be_typed_as_a_table() -> None:
    """The case ADR-026's exclusion made unreachable and ADR-028 restored.

    Brinton's tables are scans: they arrive as picture blocks, and before this the most narratable
    block type in the book could only come back chart, diagram, or unknown.
    """
    client = FakeClient({"type": "table", "certainty": 0.9})
    result = classify(_block(caption="Fig. 8."), tier=Tier.GPU, client=client)

    assert result.type is DescriptionType.TABLE
    assert result.evidence is Evidence.MODEL


def test_the_table_answer_only_ever_applies_to_a_picture_of_a_table() -> None:
    """The distinction ADR-028 rests on, guarded rather than assumed.

    A table Docling extracted cleanly is typed by the parser from its own cells and never becomes
    a classifier input at all. Only a table that arrived as an image can reach this answer, and
    such a table has no cells to render — so the structural path is untouched by the change.
    """
    from asoy.parser import Block, BlockKind, NonText

    structural = Block(
        kind=BlockKind.NON_TEXT,
        non_text=NonText(
            type=DescriptionType.TABLE,
            locator="table[0]",
            table=(("Name", "Year"), ("Ada", "1843")),
        ),
    )
    scanned = Block(
        kind=BlockKind.NON_TEXT,
        non_text=NonText(type=DescriptionType.UNKNOWN, locator="picture[0]", table=None),
    )

    assert structural.non_text is not None and structural.non_text.table is not None
    assert scanned.non_text is not None and scanned.non_text.table is None

    # The assembler renders the structural one from its cells and never consults the classifier.
    from asoy.assemble import _description_for
    from asoy.fences import DescriptionSource

    rendered = _description_for(structural.non_text)
    assert rendered.source is DescriptionSource.STRUCTURE
    assert "Ada" in rendered.body

    # The scanned one carries no cells, so a structural render is not available to it.
    assert _description_for(scanned.non_text).source is DescriptionSource.MODEL


# --- Batching -----------------------------------------------------------------------------------


def test_classify_all_keeps_order_and_makes_one_call_per_block() -> None:
    client = _answer("chart", 0.9)
    blocks = [_block(locator=f"picture[{index}]") for index in range(3)]
    blocks[1] = _block(locator="picture[1]", caption="A photograph of the bay")

    results = classify_all(blocks, tier=Tier.GPU, client=client)

    assert [r.type for r in results] == [
        DescriptionType.CHART,
        DescriptionType.PHOTOGRAPH,
        DescriptionType.CHART,
    ]
    assert len(client.calls) == 2, "the caption-settled block costs no call"


def test_one_failure_does_not_stop_the_rest() -> None:
    class FlakyClient(FakeClient):
        def generate(self, **kwargs: Any) -> FakeResponse:
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise ConnectionError("dropped")
            return FakeResponse(response=json.dumps({"type": "chart", "certainty": 0.9}))

    results = classify_all([_block(), _block()], tier=Tier.GPU, client=FlakyClient())
    assert [r.type for r in results] == [DescriptionType.UNKNOWN, DescriptionType.CHART]


# --- Invariant 1 --------------------------------------------------------------------------------


def test_the_classifier_reaches_nothing_but_ollama() -> None:
    """Invariant 1. The only permitted destination is the local Ollama endpoint.

    A static check, because the runtime path is exercised with a stand-in client that could not
    reach anything even if the code tried.
    """
    from pathlib import Path

    import asoy.classifier

    package = Path(asoy.classifier.__file__).parent
    for source in sorted(package.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        for forbidden in ("requests", "urllib", "httpx", "http.client", "socket", "aiohttp"):
            assert forbidden not in text, f"{source} names {forbidden}"


def test_classification_is_a_plain_record() -> None:
    """It reaches the job record and the review UI, so it must carry no live handles."""
    result = classify(_block(), tier=Tier.GPU, client=_answer("chart", 0.9))
    assert isinstance(result, Classification)
    assert isinstance(result.certainty, float)
    assert isinstance(result.detail, str)
