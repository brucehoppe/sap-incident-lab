from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from sap_incident_lab.config import Settings

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    root = tmp_path / "incidents"
    output = tmp_path / "outputs"
    root.mkdir()
    output.mkdir()
    return Settings(root=root, output=output)


@pytest.fixture
def synthetic_incident(settings: Settings) -> Settings:
    """Copy the committed INC-SYN-001 fixture into settings.root.

    Copying rather than pointing at the checked-in fixture directly means
    tests that mutate a file (the SOURCE_CHANGED case) never touch the repo
    copy.
    """
    assert settings.root is not None
    shutil.copytree(
        FIXTURES_DIR / "INC-SYN-001",
        settings.root / "INC-SYN-001",
        ignore=shutil.ignore_patterns("evaluation-private.md"),
    )
    return settings
