from __future__ import annotations

from sap_incident_lab.analysis.schemas import (
    ModelExtraction,
    Observation,
    SourceRef,
    TimelineEntry,
)
from sap_incident_lab.analysis.validate import clip_invalid_refs


def test_valid_refs_are_kept_unchanged() -> None:
    extraction = ModelExtraction(
        observations=[
            Observation(id="o1", text="lock held", refs=[SourceRef(start_line=5, end_line=6)])
        ]
    )
    filtered, dropped = clip_invalid_refs(extraction, start_line=1, end_line=10)
    assert dropped == 0
    assert filtered.observations[0].refs == [SourceRef(start_line=5, end_line=6)]


def test_observation_with_all_refs_out_of_range_is_dropped() -> None:
    extraction = ModelExtraction(
        observations=[
            Observation(id="o1", text="hallucinated", refs=[SourceRef(start_line=50, end_line=51)])
        ]
    )
    filtered, dropped = clip_invalid_refs(extraction, start_line=1, end_line=10)
    assert dropped == 1
    assert filtered.observations == []


def test_observation_with_no_refs_is_kept() -> None:
    extraction = ModelExtraction(observations=[Observation(id="o1", text="no citation given")])
    filtered, dropped = clip_invalid_refs(extraction, start_line=1, end_line=10)
    assert dropped == 0
    assert len(filtered.observations) == 1


def test_partially_bad_refs_keeps_only_the_good_ones() -> None:
    extraction = ModelExtraction(
        observations=[
            Observation(
                id="o1",
                text="mixed",
                refs=[SourceRef(start_line=2, end_line=2), SourceRef(start_line=99, end_line=99)],
            )
        ]
    )
    filtered, dropped = clip_invalid_refs(extraction, start_line=1, end_line=10)
    assert dropped == 1
    assert filtered.observations[0].refs == [SourceRef(start_line=2, end_line=2)]


def test_timeline_entry_with_bad_ref_is_dropped() -> None:
    extraction = ModelExtraction(
        timeline=[
            TimelineEntry(event="ok", ref=SourceRef(start_line=3, end_line=3)),
            TimelineEntry(event="bad", ref=SourceRef(start_line=999, end_line=999)),
            TimelineEntry(event="no ref given", ref=None),
        ]
    )
    filtered, dropped = clip_invalid_refs(extraction, start_line=1, end_line=10)
    assert dropped == 1
    assert [e.event for e in filtered.timeline] == ["ok", "no ref given"]


def test_ref_spanning_outside_the_chunk_boundary_is_rejected() -> None:
    # starts inside the chunk but extends past its end -> still invalid
    extraction = ModelExtraction(
        observations=[
            Observation(id="o1", text="spans boundary", refs=[SourceRef(start_line=9, end_line=12)])
        ]
    )
    filtered, dropped = clip_invalid_refs(extraction, start_line=1, end_line=10)
    assert dropped == 1
    assert filtered.observations == []
