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


def _copy_fixture(settings: Settings, incident_id: str) -> None:
    """Copy one committed fixture into settings.root.

    Copying rather than pointing at the checked-in fixture directly means
    tests that mutate a file (the SOURCE_CHANGED case) never touch the repo
    copy. evaluation-private.md never goes in — it lives outside the
    evidence root in the real layout too (DESIGN.md section 5).
    """
    assert settings.root is not None
    shutil.copytree(
        FIXTURES_DIR / incident_id,
        settings.root / incident_id,
        ignore=shutil.ignore_patterns("evaluation-private.md"),
    )


@pytest.fixture
def synthetic_incident(settings: Settings) -> Settings:
    """settings.root containing only INC-SYN-001 (the enqueue-lock case)."""
    _copy_fixture(settings, "INC-SYN-001")
    return settings


@pytest.fixture
def synthetic_incident_portfolio(settings: Settings) -> Settings:
    """settings.root containing all four synthetic incidents, covering
    distinct failure shapes: a stale enqueue lock, an infinite-loop batch
    job, a memory-exhaustion short dump, and an expired RFC certificate."""
    for incident_id in ("INC-SYN-001", "INC-SYN-002", "INC-SYN-003", "INC-SYN-004"):
        _copy_fixture(settings, incident_id)
    return settings
