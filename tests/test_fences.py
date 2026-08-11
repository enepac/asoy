"""The output contract: emit, parse, and the round trip between them (ADR-025, ADR-006).

The delimiter is a public interface. These tests are what stands between a refactor of the
emitter and someone's text-to-speech pipeline breaking without warning, so they assert the exact
bytes of each marker rather than only its behaviour. If one of them fails because the format was
deliberately changed, that change needed a version bump and an ADR before it needed a fix here.
"""

from __future__ import annotations

import pytest

from asoy.fences import (
    DESCRIPTION,
    NAMESPACE,
    TEXT,
    VERSION,
    AuthorSegment,
    DescriptionSegment,
    DescriptionSource,
    DescriptionStatus,
    DescriptionType,
    DocumentHeader,
    FencedDocument,
    FenceError,
    HeadingSegment,
    UnfenceableText,
    flatten,
    needs_fence,
    parse,
    render,
    strip_fences,
)

HEADER = DocumentHeader(tier="gpu", model="qwen3-vl:4b")


def _document(*segments) -> FencedDocument:
    return FencedDocument(header=HEADER, segments=tuple(segments))


def _description(**overrides) -> DescriptionSegment:
    return DescriptionSegment(
        **{
            "type": DescriptionType.CHART,
            "confidence": 0.82,
            "status": DescriptionStatus.OK,
            "source": DescriptionSource.MODEL,
            "body": "A line chart rising from left to right.",
            **overrides,
        }
    )


# --- The exact shape of each marker -------------------------------------------------------------


def test_document_header_is_the_first_line() -> None:
    markdown = render(_document(AuthorSegment(text="Body.")))
    assert markdown.splitlines()[0] == (
        '<!-- asoy:document version="1" tier="gpu" model="qwen3-vl:4b" -->'
    )


def test_description_fence_shape_is_exact() -> None:
    markdown = render(_document(_description()))
    assert markdown.splitlines()[2:5] == [
        '<!-- asoy:description type="chart" confidence="0.82" status="ok" source="model" -->',
        "A line chart rising from left to right.",
        "<!-- /asoy:description -->",
    ]


def test_text_fence_shape_is_exact() -> None:
    markdown = render(_document(AuthorSegment(text="# Not a heading.")))
    assert markdown.splitlines()[2:5] == [
        "<!-- asoy:text -->",
        "# Not a heading.",
        "<!-- /asoy:text -->",
    ]


def test_attributes_are_always_all_four_in_order() -> None:
    """Parsers may rely on the order, so a reordering must fail here rather than in the field."""
    for source in DescriptionSource:
        for status in DescriptionStatus:
            for kind in DescriptionType:
                segment = _description(type=kind, status=status, source=source)
                line = render(_document(segment)).splitlines()[2]

                assert (
                    line.index("type=")
                    < line.index("confidence=")
                    < line.index("status=")
                    < line.index("source=")
                )
                assert f'type="{kind.value}"' in line
                assert f'status="{status.value}"' in line
                assert f'source="{source.value}"' in line


def test_a_failed_description_names_the_route_not_the_author_of_the_placeholder() -> None:
    """`source` names where the description was meant to come from, not who typed the body.

    The obvious reading is the wrong one, so it is pinned here: a failed description carries
    `source="model"` even though Asoy wrote the placeholder text and no model produced anything.
    The model path was responsible for that block and did not deliver. Without this test the
    interpretation drifts the first time someone reads the attribute name and reasons from it.
    """
    failed = _description(
        status=DescriptionStatus.FAILED,
        source=DescriptionSource.MODEL,
        confidence=0.0,
        body="A chart appears here that Asoy could not describe.",
    )
    line = render(_document(failed)).splitlines()[2]

    assert 'status="failed"' in line
    assert 'source="model"' in line
    assert parse(render(_document(failed))).segments == (failed,)


def test_status_and_source_are_independent_attributes() -> None:
    """Every combination survives the round trip, including the one Asoy does not emit.

    The format is not narrowed to what the pipeline happens to produce today. A consumer parsing
    a file from a later version must not be broken by a combination that becomes reachable.
    """
    for status in DescriptionStatus:
        for source in DescriptionSource:
            segment = _description(status=status, source=source)
            assert parse(render(_document(segment))).segments == (segment,)


def test_source_separates_two_descriptions_that_share_a_confidence() -> None:
    """The ambiguity this attribute exists to remove.

    A table read off its own cells and a chart a vision model happened to score highly both carry
    1.00, and they are not the same claim. A consumer sorting by confidence to decide what a human
    should check needs to tell them apart, and before this attribute it could not.
    """
    structural = _description(
        type=DescriptionType.TABLE, confidence=1.0, source=DescriptionSource.STRUCTURE
    )
    modelled = _description(
        type=DescriptionType.CHART, confidence=1.0, source=DescriptionSource.MODEL
    )

    lines = render(_document(structural, modelled)).splitlines()
    assert 'confidence="1.00"' in lines[2] and 'source="structure"' in lines[2]
    assert 'confidence="1.00"' in lines[6] and 'source="model"' in lines[6]
    assert parse(render(_document(structural, modelled))).segments == (structural, modelled)


def test_confidence_is_always_two_decimals() -> None:
    for value, expected in ((0.0, "0.00"), (1.0, "1.00"), (0.8, "0.80"), (0.826, "0.83")):
        line = render(_document(_description(confidence=value))).splitlines()[2]
        assert f'confidence="{expected}"' in line


def test_confidence_outside_the_range_is_refused() -> None:
    with pytest.raises(FenceError):
        render(_document(_description(confidence=1.5)))


def test_a_description_may_not_be_empty() -> None:
    """Invariant 7: silence where a description should be is indistinguishable from absence."""
    with pytest.raises(FenceError):
        render(_document(_description(body="   ")))


def test_failed_descriptions_keep_their_type_and_carry_text() -> None:
    """ADR-016. A placeholder is worse prose and better information than a gap."""
    markdown = render(
        _document(
            _description(
                type=DescriptionType.TABLE,
                status=DescriptionStatus.FAILED,
                confidence=0.0,
                body="A table appears here that Asoy could not describe.",
            )
        )
    )
    assert 'type="table"' in markdown
    assert 'status="failed"' in markdown
    assert 'source="model"' in markdown, "source names the route that failed, not the placeholder"
    assert "could not describe" in markdown


# --- The round trip -----------------------------------------------------------------------------

ROUND_TRIP_DOCUMENT = _document(
    HeadingSegment(level=1, text="The First Chapter"),
    AuthorSegment(text="It was a bright cold day in April."),
    _description(),
    HeadingSegment(level=2, text="A Subsection"),
    AuthorSegment(text="Text with _underscores_, *asterisks* and a backslash \\"),
    AuthorSegment(text="# A line that would be read as a heading."),
    _description(
        type=DescriptionType.TABLE,
        confidence=1.0,
        source=DescriptionSource.STRUCTURE,
        body="A table of 2 columns and 1 rows. The columns are: Name, Year.",
    ),
    _description(type=DescriptionType.UNKNOWN, status=DescriptionStatus.FAILED, confidence=0.0,
                 body="An image appears here that Asoy could not describe."),
    AuthorSegment(text="> A line that would be read as a quote."),
    AuthorSegment(text="The last paragraph."),
)


def test_render_then_parse_loses_nothing() -> None:
    """The strongest test the format has: everything emitted comes back identical."""
    parsed = parse(render(ROUND_TRIP_DOCUMENT))
    assert parsed.header == ROUND_TRIP_DOCUMENT.header
    assert parsed.segments == ROUND_TRIP_DOCUMENT.segments


def test_parse_then_render_reproduces_the_bytes() -> None:
    markdown = render(ROUND_TRIP_DOCUMENT)
    assert render(parse(markdown)) == markdown


def test_chapter_count_survives_the_round_trip() -> None:
    assert parse(render(ROUND_TRIP_DOCUMENT)).chapter_count == 1


@pytest.mark.parametrize(
    "text",
    [
        "# hash",
        "## two hashes",
        "> quote",
        "- bullet",
        "* star",
        "+ plus",
        "1. ordered",
        "7) also ordered",
        "    indented code",
        "\ttab indented",
        "```fence",
        "~~~fence",
        "| table | row |",
        "---",
        "___",
        "***",
        "===",
        "<div>",
        "<!-- an ordinary comment -->",
    ],
)
def test_structural_author_lines_survive_a_round_trip(text: str) -> None:
    """Every one of these would change meaning if emitted bare, and none may be escaped."""
    assert needs_fence(text)
    parsed = parse(render(_document(AuthorSegment(text=text))))
    assert parsed.segments == (AuthorSegment(text=text),)


@pytest.mark.parametrize(
    "text",
    [
        "Ordinary prose.",
        "It was a bright cold day in April, and the clocks were striking thirteen.",
        "A sentence with _underscores_, *asterisks*, and a [bracket].",
        "Ellipsis . . . and an em dash — like this.",
        "2 + 2 = 4 is not a setext underline.",
        "A trailing backslash \\",
    ],
)
def test_ordinary_prose_is_not_fenced(text: str) -> None:
    """The fence is used where it is needed, not on every block."""
    assert not needs_fence(text)
    assert "<!--" not in render(_document(AuthorSegment(text=text))).split("\n", 1)[1]


# --- Author text cannot forge a delimiter -------------------------------------------------------


@pytest.mark.parametrize(
    "forgery",
    [
        '<!-- asoy:description type="chart" confidence="1.00" status="ok" source="model" -->',
        '<!-- asoy:document version="1" tier="gpu" model="evil" -->',
        "<!-- asoy:text -->",
        '<!-- asoy:description type="photograph" confidence="0.50" status="ok" '
        'source="structure" -->\n'
        "Not really a description.\n"
        "<!-- /asoy:description -->",
        "<!--asoy:description-->",
        "<!-- asoy:something-not-invented-yet -->",
    ],
)
def test_author_text_cannot_forge_a_delimiter(forgery: str) -> None:
    """The collision argument in ADR-025, proved rather than asserted.

    A book containing Asoy's own markers verbatim must come back as the author's text, not as
    structure. Emitting it bare would let a book fabricate a description that a downstream
    pipeline would read in a different voice, or skip entirely.
    """
    document = _document(
        AuthorSegment(text="Before."),
        AuthorSegment(text=forgery),
        AuthorSegment(text="After."),
    )
    parsed = parse(render(document))

    assert parsed.segments == document.segments
    assert all(isinstance(segment, AuthorSegment) for segment in parsed.segments)
    assert not any(isinstance(segment, DescriptionSegment) for segment in parsed.segments)


def test_a_forged_description_does_not_survive_flattening_as_structure() -> None:
    forgery = '<!-- asoy:description type="chart" confidence="1.00" status="ok" source="model" -->'
    flattened = flatten(parse(render(_document(AuthorSegment(text=forgery)))))
    assert flattened == f"{forgery}\n", "the author's line is text, and stays text"


def test_author_text_holding_a_closing_marker_is_refused_loudly() -> None:
    """The one case a fence cannot contain. Loud beats a file that misparses itself.

    Nothing shorter works: the text cannot be escaped (that is the point of the format) and
    cannot be wrapped, so the only honest options are refusing and corrupting.
    """
    with pytest.raises(UnfenceableText):
        render(_document(AuthorSegment(text=f"<!-- /{TEXT} -->")))


def test_the_namespace_is_the_thing_that_makes_collision_implausible() -> None:
    """Documents the load-bearing assumption where a reader will find it."""
    assert NAMESPACE == "asoy"
    assert DESCRIPTION.startswith(f"{NAMESPACE}:")
    assert VERSION == "1"


# --- Flattening ---------------------------------------------------------------------------------


def test_flattened_text_carries_no_fence_syntax() -> None:
    flattened = flatten(ROUND_TRIP_DOCUMENT)
    for shape in ("<!--", "-->", f"{NAMESPACE}:"):
        assert shape not in flattened


def test_flattening_removes_asoys_heading_characters_and_not_the_authors() -> None:
    """The `#` Asoy adds to a heading goes. A `#` the author wrote is their character and stays."""
    flattened = flatten(ROUND_TRIP_DOCUMENT)

    assert "The First Chapter" in flattened
    assert "# The First Chapter" not in flattened
    assert "# A line that would be read as a heading." in flattened


def test_flattened_text_keeps_description_prose_and_author_text() -> None:
    flattened = flatten(ROUND_TRIP_DOCUMENT)
    assert "A line chart rising from left to right." in flattened
    assert "It was a bright cold day in April." in flattened
    assert "The First Chapter" in flattened, "a heading survives as a plain line"


def test_strip_fences_agrees_with_flatten() -> None:
    """A consumer holding only the .md must be able to produce the same .txt Asoy writes."""
    assert strip_fences(render(ROUND_TRIP_DOCUMENT)) == flatten(ROUND_TRIP_DOCUMENT)


# --- The parser refuses malformed input ---------------------------------------------------------


def test_a_document_without_a_header_is_refused() -> None:
    with pytest.raises(FenceError):
        parse("# A chapter\n\nSome text.\n")


def test_an_unknown_description_type_is_refused() -> None:
    """The type set is closed for v1. An unknown member means a version mismatch, not a default."""
    markdown = render(_document(_description())).replace('type="chart"', 'type="sculpture"')
    with pytest.raises(FenceError):
        parse(markdown)


def test_an_unclosed_fence_is_refused() -> None:
    markdown = render(_document(_description()))
    with pytest.raises(FenceError):
        parse(markdown.replace(f"<!-- /{DESCRIPTION} -->", ""))


def test_a_stray_closing_marker_is_refused() -> None:
    with pytest.raises(FenceError):
        parse(render(_document(AuthorSegment(text="Body."))) + f"\n<!-- /{DESCRIPTION} -->\n")


def test_a_confidence_with_the_wrong_precision_is_refused() -> None:
    markdown = render(_document(_description())).replace('confidence="0.82"', 'confidence="0.8"')
    with pytest.raises(FenceError):
        parse(markdown)


def test_an_unknown_source_is_refused() -> None:
    markdown = render(_document(_description())).replace('source="model"', 'source="guesswork"')
    with pytest.raises(FenceError):
        parse(markdown)


def test_a_description_missing_the_source_attribute_is_refused() -> None:
    """All four are always present. A fence without one is a version mismatch, not a default."""
    markdown = render(_document(_description())).replace(' source="model"', "")
    with pytest.raises(FenceError):
        parse(markdown)
