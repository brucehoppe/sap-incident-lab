from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from sap_incident_lab import errors
from sap_incident_lab.config import Settings
from sap_incident_lab.evidence.registry import (
    describe_files,
    get_file,
    list_incidents,
    load_files,
    read_evidence_window,
    search_evidence,
)


def test_list_incidents_finds_the_synthetic_fixture(synthetic_incident: Settings) -> None:
    assert list_incidents(synthetic_incident) == ["INC-SYN-001"]


def test_list_incidents_skips_dirs_without_a_manifest(synthetic_incident: Settings) -> None:
    assert synthetic_incident.root is not None
    (synthetic_incident.root / "not-an-incident").mkdir()
    assert list_incidents(synthetic_incident) == ["INC-SYN-001"]


def test_list_incidents_raises_config_invalid_without_root(tmp_path: Path) -> None:
    with pytest.raises(errors.ToolError) as excinfo:
        list_incidents(Settings())
    assert excinfo.value.code == "CONFIG_INVALID"


def test_load_files_assigns_stable_ids_in_manifest_order(
    synthetic_incident: Settings,
) -> None:
    manifest, records = load_files(synthetic_incident, "INC-SYN-001")
    assert [r.file_id for r in records] == ["f01", "f02"]
    assert [r.rel_path for r in records] == ["import-log.txt", "workprocess-trace.txt"]
    assert manifest.incident_id == "INC-SYN-001"


def test_load_files_computes_correct_sha256(synthetic_incident: Settings) -> None:
    assert synthetic_incident.root is not None
    path = synthetic_incident.root / "INC-SYN-001" / "import-log.txt"
    expected = hashlib.sha256(path.read_bytes()).hexdigest()

    record = get_file(synthetic_incident, "INC-SYN-001", "f01")
    assert record.sha256 == expected


def test_unknown_incident_id_pattern_raises_not_found(synthetic_incident: Settings) -> None:
    with pytest.raises(errors.ToolError) as excinfo:
        load_files(synthetic_incident, "../etc")
    assert excinfo.value.code == "INCIDENT_NOT_FOUND"


def test_unknown_file_id_raises_file_not_found(synthetic_incident: Settings) -> None:
    with pytest.raises(errors.ToolError) as excinfo:
        get_file(synthetic_incident, "INC-SYN-001", "f99")
    assert excinfo.value.code == "FILE_NOT_FOUND"


def test_manifest_path_escaping_incident_dir_is_rejected(synthetic_incident: Settings) -> None:
    assert synthetic_incident.root is not None
    incident_dir = synthetic_incident.root / "INC-SYN-001"
    manifest_path = incident_dir / "incident.json"
    manifest_path.write_text(
        manifest_path.read_text().replace("import-log.txt", "../outside.txt")
    )
    (synthetic_incident.root.parent / "outside.txt").write_text("secret\n")

    with pytest.raises(errors.ToolError) as excinfo:
        load_files(synthetic_incident, "INC-SYN-001")
    assert excinfo.value.code == "PATH_REJECTED"


def test_oversize_file_is_rejected(synthetic_incident: Settings) -> None:
    synthetic_incident.max_file_mb = 1
    # ge=1 is the field's floor; shrink the effective limit for the test instead
    # by writing a file bigger than 1 MB.
    assert synthetic_incident.root is not None
    big = synthetic_incident.root / "INC-SYN-001" / "import-log.txt"
    big.write_bytes(b"x" * (2 * 1024 * 1024))

    with pytest.raises(errors.ToolError) as excinfo:
        load_files(synthetic_incident, "INC-SYN-001")
    assert excinfo.value.code == "FILE_TOO_LARGE"


def test_decode_failure_is_reported_not_silently_replaced(synthetic_incident: Settings) -> None:
    assert synthetic_incident.root is not None
    bad = synthetic_incident.root / "INC-SYN-001" / "import-log.txt"
    bad.write_bytes(b"valid line\n\xff\xfe invalid utf-8 bytes\n")

    with pytest.raises(errors.ToolError) as excinfo:
        load_files(synthetic_incident, "INC-SYN-001")
    assert excinfo.value.code == "DECODE_FAILED"


def test_bom_is_stripped_from_line_numbering_but_kept_in_hash(
    synthetic_incident: Settings,
) -> None:
    assert synthetic_incident.root is not None
    path = synthetic_incident.root / "INC-SYN-001" / "import-log.txt"
    raw_with_bom = b"\xef\xbb\xbffirst line\nsecond line\n"
    path.write_bytes(raw_with_bom)
    expected_hash = hashlib.sha256(raw_with_bom).hexdigest()

    record = get_file(synthetic_incident, "INC-SYN-001", "f01")
    assert record.sha256 == expected_hash  # BOM bytes are still hashed
    assert record.lines[0] == "first line"  # but not in the decoded text


def test_describe_files_shape(synthetic_incident: Settings) -> None:
    manifest, records = load_files(synthetic_incident, "INC-SYN-001")
    described = describe_files(manifest, records)
    assert described["incident_id"] == "INC-SYN-001"
    assert described["system"]["release"] is None
    assert {f["file_id"] for f in described["files"]} == {"f01", "f02"}


def test_read_evidence_window_returns_exact_numbered_lines(
    synthetic_incident: Settings,
) -> None:
    record = get_file(synthetic_incident, "INC-SYN-001", "f01")
    result = read_evidence_window(
        synthetic_incident, "INC-SYN-001", "f01", 1, 2, expected_sha256=record.sha256
    )
    assert result["lines"][0]["line"] == 1
    assert result["lines"][0]["text"] == record.lines[0]
    assert result["lines"][1]["line"] == 2
    assert result["clipped"] is False


def test_read_evidence_window_detects_source_changed(synthetic_incident: Settings) -> None:
    with pytest.raises(errors.ToolError) as excinfo:
        read_evidence_window(
            synthetic_incident, "INC-SYN-001", "f01", 1, 2, expected_sha256="0" * 64
        )
    assert excinfo.value.code == "SOURCE_CHANGED"


def test_read_evidence_window_rejects_invalid_range(synthetic_incident: Settings) -> None:
    with pytest.raises(errors.ToolError) as excinfo:
        read_evidence_window(synthetic_incident, "INC-SYN-001", "f01", 5, 2, None)
    assert excinfo.value.code == "RANGE_INVALID"


def test_read_evidence_window_clips_and_reports_next_start(
    synthetic_incident: Settings,
) -> None:
    synthetic_incident.evidence_max_lines = 1
    record = get_file(synthetic_incident, "INC-SYN-001", "f01")
    result = read_evidence_window(
        synthetic_incident, "INC-SYN-001", "f01", 1, record.line_count, None
    )
    assert result["clipped"] is True
    assert result["next_start_line"] == 2
    assert len(result["lines"]) == 1


def test_search_evidence_returns_exact_citation_lines(synthetic_incident: Settings) -> None:
    result = search_evidence(synthetic_incident, "INC-SYN-001", "ALREADY HELD")
    assert result["truncated"] is False
    assert result["matches"][0]["file_id"] == "f02"
    assert result["matches"][0]["line"] == 3
    assert len(result["matches"][0]["sha256"]) == 64


def test_search_evidence_rejects_empty_query(synthetic_incident: Settings) -> None:
    with pytest.raises(errors.ToolError) as excinfo:
        search_evidence(synthetic_incident, "INC-SYN-001", " ")
    assert excinfo.value.code == "QUERY_INVALID"


def test_list_incidents_finds_the_full_portfolio(
    synthetic_incident_portfolio: Settings,
) -> None:
    assert list_incidents(synthetic_incident_portfolio) == [
        "INC-SYN-001",
        "INC-SYN-002",
        "INC-SYN-003",
        "INC-SYN-004",
    ]


@pytest.mark.parametrize(
    "incident_id", ["INC-SYN-001", "INC-SYN-002", "INC-SYN-003", "INC-SYN-004"]
)
def test_each_portfolio_incident_loads_two_hashed_files(
    synthetic_incident_portfolio: Settings, incident_id: str
) -> None:
    manifest, records = load_files(synthetic_incident_portfolio, incident_id)
    assert manifest.incident_id == incident_id
    assert len(records) == 2
    assert all(len(r.sha256) == 64 for r in records)
    assert all(r.line_count > 0 for r in records)


def test_inventory_excludes_incident_symlinks_outside_root(synthetic_incident: Settings, tmp_path: Path) -> None:
    import shutil

    assert synthetic_incident.root is not None
    outside = tmp_path / "outside"
    shutil.move(str(synthetic_incident.root / "INC-SYN-001"), outside)
    (synthetic_incident.root / "INC-SYN-001").symlink_to(outside, target_is_directory=True)
    assert list_incidents(synthetic_incident) == []
