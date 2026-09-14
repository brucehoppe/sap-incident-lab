from __future__ import annotations

from pathlib import Path

import pytest

from sap_incident_lab.evidence.paths import (
    PathRejected,
    resolve_evidence_path,
    resolve_incident_dir,
)


@pytest.fixture
def incident_dir(tmp_path: Path) -> Path:
    root = tmp_path / "incidents"
    incident = root / "INC-001"
    incident.mkdir(parents=True)
    (incident / "log.txt").write_text("line one\n")
    return root


def test_resolves_a_valid_relative_path(incident_dir: Path) -> None:
    resolved = resolve_evidence_path(incident_dir, "INC-001", "log.txt")
    assert resolved.name == "log.txt"


@pytest.mark.parametrize(
    "bad_rel_path",
    [
        "../log.txt",
        "sub/../../log.txt",
        "/etc/passwd",
        "C:\\Windows\\log.txt",
        "log.txt:hidden-stream",
        "\\\\server\\share\\log.txt",
        "",
    ],
)
def test_rejects_escaping_or_malformed_relative_paths(
    incident_dir: Path, bad_rel_path: str
) -> None:
    with pytest.raises(PathRejected):
        resolve_evidence_path(incident_dir, "INC-001", bad_rel_path)


def test_rejects_path_to_a_directory(incident_dir: Path) -> None:
    (incident_dir / "INC-001" / "subdir").mkdir()
    with pytest.raises(PathRejected):
        resolve_evidence_path(incident_dir, "INC-001", "subdir")


def test_rejects_missing_file(incident_dir: Path) -> None:
    with pytest.raises(PathRejected):
        resolve_evidence_path(incident_dir, "INC-001", "missing.txt")


def test_symlink_escaping_incident_dir_is_rejected(tmp_path: Path, incident_dir: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret\n")
    (incident_dir / "INC-001" / "escape.txt").symlink_to(outside)

    with pytest.raises(PathRejected):
        resolve_evidence_path(incident_dir, "INC-001", "escape.txt")


def test_symlink_within_incident_dir_is_allowed(incident_dir: Path) -> None:
    real = incident_dir / "INC-001" / "log.txt"
    link = incident_dir / "INC-001" / "log-link.txt"
    link.symlink_to(real)

    resolved = resolve_evidence_path(incident_dir, "INC-001", "log-link.txt")
    assert resolved.read_text() == "line one\n"


def test_resolve_incident_dir_rejects_nonexistent(incident_dir: Path) -> None:
    with pytest.raises(PathRejected):
        resolve_incident_dir(incident_dir, "NOPE")
