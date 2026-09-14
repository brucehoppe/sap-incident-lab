from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sap_incident_lab.evidence.paths import PathRejected, resolve_evidence_path

# These prove the Windows-specific escapes DESIGN.md section 7 calls out
# (junctions, alternate data streams) actually fail on the OS where they
# matter -- the syntax-level rejection in paths.py runs unconditionally on
# every OS (see test_paths.py), but only a real Windows filesystem can prove
# a junction or an ADS was actually blocked rather than just spelled oddly.
pytestmark = [
    pytest.mark.windows_only,
    pytest.mark.skipif(sys.platform != "win32", reason="requires real Windows junctions/ADS"),
]


@pytest.fixture
def incident_dir(tmp_path: Path) -> Path:
    root = tmp_path / "incidents"
    incident = root / "INC-001"
    incident.mkdir(parents=True)
    (incident / "log.txt").write_text("line one\n")
    return root


def test_junction_escaping_incident_dir_is_rejected(tmp_path: Path, incident_dir: Path) -> None:
    import _winapi  # available only on Windows

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret\n")

    junction = incident_dir / "INC-001" / "escape"
    _winapi.CreateJunction(str(outside), str(junction))

    with pytest.raises(PathRejected):
        resolve_evidence_path(incident_dir, "INC-001", "escape\\secret.txt")


def test_junction_within_incident_dir_still_resolves(
    tmp_path: Path, incident_dir: Path
) -> None:
    """A junction is not rejected merely for being a junction -- only for
    landing outside the incident directory (parallels the symlink case in
    test_paths.py::test_symlink_within_incident_dir_is_allowed)."""
    import _winapi

    inside_target = incident_dir / "INC-001" / "real_subdir"
    inside_target.mkdir()
    (inside_target / "note.txt").write_text("fine\n")

    junction = incident_dir / "INC-001" / "linked_subdir"
    _winapi.CreateJunction(str(inside_target), str(junction))

    resolved = resolve_evidence_path(incident_dir, "INC-001", "linked_subdir\\note.txt")
    assert resolved.read_text() == "fine\n"


def test_alternate_data_stream_is_rejected_even_when_it_really_exists(
    incident_dir: Path,
) -> None:
    target = incident_dir / "INC-001" / "log.txt"
    # A real NTFS alternate data stream on an existing, otherwise-legitimate
    # evidence file -- not just an oddly spelled path.
    with open(f"{target}:hidden", "w", encoding="utf-8") as f:
        f.write("hidden content\n")

    with pytest.raises(PathRejected):
        resolve_evidence_path(incident_dir, "INC-001", "log.txt:hidden")
