from __future__ import annotations

import json
from pathlib import Path

import pytest

from sap_incident_lab.evidence.manifest import ManifestError, load_manifest


def test_loads_the_synthetic_fixture_manifest(fixtures_dir: Path) -> None:
    manifest = load_manifest(fixtures_dir / "INC-SYN-001")
    assert manifest.incident_id == "INC-SYN-001"
    assert {f.path for f in manifest.files} == {"import-log.txt", "workprocess-trace.txt"}
    assert manifest.system.release is None  # unknown facts stay null, never guessed


def test_missing_manifest_raises(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="no incident.json"):
        load_manifest(tmp_path)


def test_malformed_json_raises(tmp_path: Path) -> None:
    (tmp_path / "incident.json").write_text("{not json")
    with pytest.raises(ManifestError, match="not valid JSON"):
        load_manifest(tmp_path)


def test_invalid_incident_id_raises(tmp_path: Path) -> None:
    (tmp_path / "incident.json").write_text(json.dumps({"incident_id": "bad id!"}))
    with pytest.raises(ManifestError, match="failed validation"):
        load_manifest(tmp_path)


@pytest.mark.parametrize(
    "incident_id", ["INC-SYN-001", "INC-SYN-002", "INC-SYN-003", "INC-SYN-004"]
)
def test_every_portfolio_fixture_has_a_valid_manifest(
    fixtures_dir: Path, incident_id: str
) -> None:
    manifest = load_manifest(fixtures_dir / incident_id)
    assert manifest.incident_id == incident_id
    assert manifest.summary
    assert len(manifest.files) == 2
