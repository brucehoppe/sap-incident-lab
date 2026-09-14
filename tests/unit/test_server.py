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


@pytest.mark.asyncio
async def test_evidence_tools_round_trip_through_the_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Exercises list_incidents -> list_files -> get_evidence as Claude would,
    through the real MCP Client, against the committed synthetic fixture."""
    import shutil

    fixtures_dir = Path(__file__).parent.parent / "fixtures"
    root = tmp_path / "incidents"
    output = tmp_path / "outputs"
    root.mkdir()
    output.mkdir()
    shutil.copytree(
        fixtures_dir / "INC-SYN-001",
        root / "INC-SYN-001",
        ignore=shutil.ignore_patterns("evaluation-private.md"),
    )
    monkeypatch.setenv("INCIDENT_LAB_ROOT", str(root))
    monkeypatch.setenv("INCIDENT_LAB_OUTPUT", str(output))
    bundle = build_server()

    async with Client(bundle.server) as client:
        incidents = await client.call_tool("incident_lab_list_incidents", {})
        assert incidents.structured_content["incident_ids"] == ["INC-SYN-001"]

        listing = await client.call_tool(
            "incident_lab_list_files", {"incident_id": "INC-SYN-001"}
        )
        files = listing.structured_content["files"]
        assert {f["file_id"] for f in files} == {"f01", "f02"}
        trace_file = next(f for f in files if f["path"] == "workprocess-trace.txt")

        evidence = await client.call_tool(
            "incident_lab_get_evidence",
            {
                "incident_id": "INC-SYN-001",
                "file_id": trace_file["file_id"],
                "start_line": 3,
                "end_line": 3,
                "expected_sha256": trace_file["sha256"],
            },
        )
        line = evidence.structured_content["lines"][0]
        assert "already held" in line["text"]

        stale = await client.call_tool(
            "incident_lab_get_evidence",
            {
                "incident_id": "INC-SYN-001",
                "file_id": trace_file["file_id"],
                "start_line": 1,
                "end_line": 1,
                "expected_sha256": "0" * 64,
            },
        )
        assert stale.structured_content["error"]["code"] == "SOURCE_CHANGED"
