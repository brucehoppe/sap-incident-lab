from __future__ import annotations

from sap_incident_lab.analysis.chunking import chunk_lines


def _lines(n: int, width: int = 10) -> list[str]:
    return [f"line-{i:04d}".ljust(width, "x") for i in range(1, n + 1)]


def test_single_small_chunk_covers_whole_range() -> None:
    lines = _lines(5)
    chunks = chunk_lines(
        "f01", lines, start_line=1, end_line=5, max_lines=120, max_chars=8000, overlap_lines=15
    )
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "f01:1-5"
    assert chunks[0].start_line == 1 and chunks[0].end_line == 5
    assert chunks[0].lines == lines


def test_splits_on_max_lines_with_overlap() -> None:
    lines = _lines(10)
    chunks = chunk_lines(
        "f01", lines, start_line=1, end_line=10, max_lines=4, max_chars=8000, overlap_lines=2
    )
    assert [c.chunk_id for c in chunks] == ["f01:1-4", "f01:3-6", "f01:5-8", "f01:7-10"]
    # consecutive chunks actually overlap by the configured amount
    assert chunks[0].lines[-2:] == chunks[1].lines[:2]


def test_splits_on_max_chars_even_within_max_lines() -> None:
    lines = ["a" * 40] * 10
    chunks = chunk_lines(
        "f01", lines, start_line=1, end_line=10, max_lines=120, max_chars=100, overlap_lines=0
    )
    assert all(c.end_line - c.start_line + 1 <= 2 for c in chunks)  # 2*40 < 100 < 3*40


def test_deterministic_same_input_same_chunk_ids() -> None:
    lines = _lines(37)
    a = chunk_lines("f01", lines, start_line=1, end_line=37, max_lines=10, max_chars=8000, overlap_lines=3)
    b = chunk_lines("f01", lines, start_line=1, end_line=37, max_lines=10, max_chars=8000, overlap_lines=3)
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]


def test_no_lines_lost_or_gapped_across_chunks_accounting_for_overlap() -> None:
    lines = _lines(23)
    chunks = chunk_lines(
        "f01", lines, start_line=1, end_line=23, max_lines=5, max_chars=8000, overlap_lines=1
    )
    covered: set[int] = set()
    for c in chunks:
        covered.update(range(c.start_line, c.end_line + 1))
    assert covered == set(range(1, 24))


def test_oversize_line_becomes_its_own_flagged_chunk() -> None:
    lines = ["short", "x" * 500, "short again"]
    chunks = chunk_lines(
        "f01", lines, start_line=1, end_line=3, max_lines=120, max_chars=100, overlap_lines=0
    )
    oversize_chunks = [c for c in chunks if c.oversize]
    assert len(oversize_chunks) == 1
    assert oversize_chunks[0].start_line == oversize_chunks[0].end_line == 2
    # the surrounding short lines are still covered by ordinary chunks
    covered = {ln for c in chunks for ln in range(c.start_line, c.end_line + 1)}
    assert covered == {1, 2, 3}


def test_partial_range_within_a_larger_file() -> None:
    lines = _lines(100)
    chunks = chunk_lines(
        "f01", lines, start_line=40, end_line=45, max_lines=120, max_chars=8000, overlap_lines=15
    )
    assert len(chunks) == 1
    assert chunks[0].start_line == 40
    assert chunks[0].end_line == 45
    assert chunks[0].lines == lines[39:45]
