from __future__ import annotations

from pathlib import Path

import pytest
from mcp import Client

from sap_incident_lab.config import get_settings
from sap_incident_lab.server import build_server


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_health_reports_config_invalid_without_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("INCIDENT_LAB_ROOT", raising=False)
    monkeypatch.delenv("INCIDENT_LAB_OUTPUT", raising=False)
    bundle = build_server()

    async with Client(bundle.server) as client:
        result = await client.call_tool("incident_lab_health", {})

    assert result.structured_content["config_valid"] is False
    assert "INCIDENT_LAB_ROOT" in result.structured_content["config_error"]


@pytest.mark.asyncio
async def test_health_reports_config_valid_with_root_and_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "incidents"
    output = tmp_path / "outputs"
    root.mkdir()
    output.mkdir()
    monkeypatch.setenv("INCIDENT_LAB_ROOT", str(root))
    monkeypatch.setenv("INCIDENT_LAB_OUTPUT", str(output))
    bundle = build_server()

    async with Client(bundle.server) as client:
        result = await client.call_tool("incident_lab_health", {})

    assert result.structured_content["config_valid"] is True
    assert result.structured_content["config_error"] is None
    assert result.structured_content["configured_model"] == "qwen3:8b"


@pytest.mark.asyncio
async def test_server_registers_health_tool() -> None:
    bundle = build_server()
    tools = await bundle.server.list_tools()
    assert {"incident_lab_health"}.issubset({t.name for t in tools})
