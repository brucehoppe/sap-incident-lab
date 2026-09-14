from __future__ import annotations

import json
from pathlib import Path

import pytest

from sap_incident_lab.config import Settings, get_settings
from sap_incident_lab.onboarding import import_incident, install_demo, setup


@pytest.fixture
def saved_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "settings/config.json"
    monkeypatch.setenv("INCIDENT_LAB_CONFIG", str(path))
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


def test_setup_rerun_preserves_evidence_and_other_servers(
    saved_config: Path, tmp_path: Path
) -> None:
    desktop = tmp_path / "desktop.json"
    original = {"theme": "dark", "mcpServers": {"other": {"command": "preserve-me"}}}
    desktop.write_text(json.dumps(original))
    first = setup(data_dir=tmp_path / "data", desktop_config=desktop, model="test-model")
    evidence = Path(first["root"]) / "untouched.txt"
    evidence.write_text("retain me")
    second = setup(desktop_config=desktop)
    assert first["root"] == second["root"]
    assert second["model"] == "test-model"
    assert evidence.read_text() == "retain me"
    merged = json.loads(desktop.read_text())
    assert merged["theme"] == "dark"
    assert merged["mcpServers"]["other"] == original["mcpServers"]["other"]
    assert merged["mcpServers"]["sap-incident-lab"]["args"][-1] == "serve"
    assert len(list(tmp_path.glob("desktop.json.bak-*"))) == 2
    assert get_settings().root == Path(first["root"])


def test_environment_overrides_saved_defaults(
    saved_config: Path, monkeypatch, tmp_path: Path
) -> None:
    setup(data_dir=tmp_path / "data", model="saved", register_desktop=False)
    monkeypatch.setenv("INCIDENT_LAB_MODEL", "override")
    assert get_settings().model == "override"


def test_invalid_desktop_config_is_not_overwritten(saved_config: Path, tmp_path: Path) -> None:
    desktop = tmp_path / "desktop.json"
    desktop.write_text('{"mcpServers": []}')
    with pytest.raises(ValueError, match="Desktop configuration"):
        setup(data_dir=tmp_path / "data", desktop_config=desktop)
    assert desktop.read_text() == '{"mcpServers": []}'
    assert not saved_config.exists()


def test_import_copies_exact_bytes_and_leaves_unknowns(settings: Settings, tmp_path: Path) -> None:
    source = tmp_path / "export.txt"
    raw = b"first\r\nsecond\r\n"
    source.write_bytes(raw)
    result = import_incident(settings, "INC-123", [source])
    assert result["files_imported"] == 1
    assert settings.root is not None
    destination = settings.root / "INC-123"
    assert (destination / "export.txt").read_bytes() == raw
    assert source.read_bytes() == raw
    manifest = json.loads((destination / "incident.json").read_text())
    assert manifest["system"]["sid"] is None
    assert manifest["time_window"]["timezone"] is None
    with pytest.raises(ValueError, match="already exists"):
        import_incident(settings, "INC-123", [source])
    assert (destination / "export.txt").read_bytes() == raw


@pytest.mark.parametrize("contents", [b"\xff", b"binary\x00file", b"x" * (1024 * 1024 + 1)])
def test_bad_import_leaves_no_incident(settings: Settings, tmp_path: Path, contents: bytes) -> None:
    settings.max_file_mb = 1
    source = tmp_path / "bad.txt"
    source.write_bytes(contents)
    with pytest.raises(ValueError):
        import_incident(settings, "INC-BAD", [source])
    assert settings.root is not None
    assert not (settings.root / "INC-BAD").exists()


def test_import_rejects_duplicate_names_and_evaluation_material(
    settings: Settings, tmp_path: Path
) -> None:
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    (first / "same.txt").write_text("one")
    (second / "SAME.txt").write_text("two")
    with pytest.raises(ValueError, match="Duplicate"):
        import_incident(settings, "INC-DUP", [first / "same.txt", second / "SAME.txt"])
    private = tmp_path / "evaluation-private.md"
    private.write_text("answer key")
    with pytest.raises(ValueError, match="reserved"):
        import_incident(settings, "INC-PRIVATE", [private])


def test_demo_contains_only_evidence(settings: Settings) -> None:
    result = install_demo(settings)
    assert result["incident_id"] == "INC-DEMO-001"
    assert settings.root is not None
    names = {p.name for p in (settings.root / "INC-DEMO-001").iterdir()}
    assert names == {"incident.json", "import-log.txt", "workprocess-trace.txt"}
