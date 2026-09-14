from __future__ import annotations

from pathlib import Path

import pytest

from sap_incident_lab import errors
from sap_incident_lab.config import Settings
from sap_incident_lab.reporting import save_report


def test_save_report_writes_a_markdown_file_under_output(synthetic_incident: Settings) -> None:
    result = save_report(synthetic_incident, "INC-SYN-001", ["job-1"], "# Findings\n\nStale lock.")
    assert synthetic_incident.output is not None
    path = synthetic_incident.output / result["path"]
    assert path.is_file()
    assert "Stale lock." in path.read_text()
    assert result["claude_authored"] is True
    assert result["mechanically_verified"] is False


def test_save_report_never_overwrites_a_prior_report(synthetic_incident: Settings) -> None:
    first = save_report(synthetic_incident, "INC-SYN-001", ["job-1"], "first version")
    second = save_report(synthetic_incident, "INC-SYN-001", ["job-2"], "second version")
    assert first["path"] != second["path"]
    assert synthetic_incident.output is not None
    assert (synthetic_incident.output / first["path"]).read_text().endswith("first version")
    assert (synthetic_incident.output / second["path"]).read_text().endswith("second version")


def test_save_report_rejects_invalid_incident_id(synthetic_incident: Settings) -> None:
    with pytest.raises(errors.ToolError) as excinfo:
        save_report(synthetic_incident, "../escape", ["job-1"], "x")
    assert excinfo.value.code == "INCIDENT_NOT_FOUND"


def test_save_report_requires_valid_config(tmp_path: Path) -> None:
    with pytest.raises(errors.ToolError) as excinfo:
        save_report(Settings(), "INC-SYN-001", [], "x")
    assert excinfo.value.code == "CONFIG_INVALID"


def test_save_report_records_job_ids_in_the_header(synthetic_incident: Settings) -> None:
    result = save_report(synthetic_incident, "INC-SYN-001", ["job-a", "job-b"], "body text")
    assert synthetic_incident.output is not None
    content = (synthetic_incident.output / result["path"]).read_text()
    assert "job-a, job-b" in content


def test_report_directory_cannot_escape_through_symlink(synthetic_incident: Settings, tmp_path: Path) -> None:
    assert synthetic_incident.output is not None
    outside = tmp_path / "outside"
    outside.mkdir()
    (synthetic_incident.output / "reports").symlink_to(outside, target_is_directory=True)
    with pytest.raises(errors.ToolError):
        save_report(synthetic_incident, "INC-SYN-001", [], "must not escape")
    assert list(outside.iterdir()) == []
