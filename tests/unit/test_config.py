from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from sap_incident_lab.config import Settings


def test_rejects_non_loopback_ollama_url() -> None:
    with pytest.raises(ValidationError, match="loopback"):
        Settings(ollama_url="http://10.0.0.5:11434")


def test_accepts_loopback_variants() -> None:
    for url in ("http://127.0.0.1:11434", "http://localhost:11434"):
        Settings(ollama_url=url)


def test_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(ValidationError, match="chunk_overlap_lines"):
        Settings(max_chunk_lines=10, chunk_overlap_lines=10)


def test_evidence_config_error_when_unset() -> None:
    settings = Settings()
    assert settings.evidence_config_error() == "INCIDENT_LAB_ROOT is not set"


def test_evidence_config_error_when_root_missing_output_set(tmp_path: Path) -> None:
    settings = Settings(output=tmp_path)
    assert settings.evidence_config_error() == "INCIDENT_LAB_ROOT is not set"


def test_evidence_config_valid(tmp_path: Path) -> None:
    root = tmp_path / "incidents"
    output = tmp_path / "outputs"
    root.mkdir()
    output.mkdir()
    settings = Settings(root=root, output=output)
    assert settings.evidence_config_error() is None


def test_evidence_config_error_when_root_is_relative() -> None:
    settings = Settings(root=Path("relative/incidents"), output=Path("/tmp/out"))
    assert "absolute" in (settings.evidence_config_error() or "")
