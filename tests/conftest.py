from __future__ import annotations

from pathlib import Path

import pytest

from sap_incident_lab.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    root = tmp_path / "incidents"
    output = tmp_path / "outputs"
    root.mkdir()
    output.mkdir()
    return Settings(root=root, output=output)
