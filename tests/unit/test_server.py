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


@pytest.mark.asyncio
async def test_job_tools_round_trip_through_the_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """start_analysis -> get_analysis -> a completed job, through the real
    MCP Client and a mocked Ollama, against the committed synthetic fixture."""
    import shutil

    import httpx

    from sap_incident_lab.analysis.schemas import ModelExtraction

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

    def handler(request: httpx.Request) -> httpx.Response:
        extraction = ModelExtraction(search_terms=["enqueue lock stale after restart"])
        return httpx.Response(
            200, json={"done_reason": "stop", "message": {"content": extraction.model_dump_json()}}
        )

    real_client = httpx.AsyncClient

    def patched(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr("sap_incident_lab.analysis.ollama_client.httpx.AsyncClient", patched)

    bundle = build_server()

    async with Client(bundle.server) as client:
        started = await client.call_tool(
            "incident_lab_start_analysis",
            {
                "incident_id": "INC-SYN-001",
                "file_ids": ["f02"],
                "question": "why did the transport import fail?",
            },
        )
        job_id = started.structured_content["job_id"]
        assert started.structured_content["state"] == "queued"

        for _ in range(50):
            result = await client.call_tool("incident_lab_get_analysis", {"job_id": job_id})
            if result.structured_content["state"] not in ("queued", "running"):
                break
            await asyncio_sleep(0.05)

        assert result.structured_content["state"] == "completed"
        assert result.structured_content["coverage"]["processed_chunks"] >= 1
        assert result.structured_content["results"][0]["extraction"]["search_terms"]


async def asyncio_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)




async def _setup_incident_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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


@pytest.mark.asyncio
async def test_start_analysis_rejects_a_second_concurrent_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import asyncio

    import httpx

    await _setup_incident_env(monkeypatch, tmp_path)

    release_event = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        await release_event.wait()
        return httpx.Response(
            200, json={"done_reason": "stop", "message": {"content": '{"observations": []}'}}
        )

    real_client = httpx.AsyncClient

    def patched(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr("sap_incident_lab.analysis.ollama_client.httpx.AsyncClient", patched)

    bundle = build_server()
    async with Client(bundle.server) as client:
        first = await client.call_tool(
            "incident_lab_start_analysis",
            {"incident_id": "INC-SYN-001", "file_ids": ["f01"], "question": "q"},
        )
        job_id = first.structured_content["job_id"]

        status = None
        for _ in range(100):
            status = await client.call_tool("incident_lab_get_analysis", {"job_id": job_id})
            if status.structured_content["state"] == "running":
                break
            await asyncio.sleep(0.01)
        assert status is not None and status.structured_content["state"] == "running"

        second = await client.call_tool(
            "incident_lab_start_analysis",
            {"incident_id": "INC-SYN-001", "file_ids": ["f02"], "question": "q"},
        )
        assert second.structured_content["error"]["code"] == "JOB_BUSY"

        release_event.set()
        for _ in range(100):
            final = await client.call_tool("incident_lab_get_analysis", {"job_id": job_id})
            if final.structured_content["state"] not in ("queued", "running", "cancelling"):
                break
            await asyncio.sleep(0.01)
        assert final.structured_content["state"] == "completed"


@pytest.mark.asyncio
async def test_job_survives_ollama_becoming_unreachable_mid_chunk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression test: an unreachable Ollama endpoint must end the job as
    'failed'/'partial' with an error message, never leave it stuck 'running'
    forever by letting the exception kill the background task silently."""
    import asyncio

    import httpx

    await _setup_incident_env(monkeypatch, tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    real_client = httpx.AsyncClient

    def patched(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr("sap_incident_lab.analysis.ollama_client.httpx.AsyncClient", patched)

    bundle = build_server()
    async with Client(bundle.server) as client:
        started = await client.call_tool(
            "incident_lab_start_analysis",
            {"incident_id": "INC-SYN-001", "file_ids": ["f01"], "question": "q"},
        )
        job_id = started.structured_content["job_id"]

        final = None
        for _ in range(100):
            final = await client.call_tool("incident_lab_get_analysis", {"job_id": job_id})
            if final.structured_content["state"] not in ("queued", "running", "cancelling"):
                break
            await asyncio.sleep(0.01)

        assert final is not None
        assert final.structured_content["state"] == "failed"
        assert "unreachable" in final.structured_content["error"].lower()


@pytest.mark.asyncio
async def test_lifespan_marks_stale_running_jobs_interrupted_on_startup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A 'running' job.json left by a previous, now-dead process must not be
    mistaken for a job this new process is managing (DESIGN.md section 9)."""
    from sap_incident_lab.jobs.store import JobRecord, JobStore, new_job_id, now_iso

    await _setup_incident_env(monkeypatch, tmp_path)
    output = Path(tmp_path / "outputs")
    store = JobStore(output)
    stale = JobRecord(
        job_id=new_job_id("INC-SYN-001"),
        incident_id="INC-SYN-001",
        file_ids=["f01"],
        question="q",
        state="running",
        created_at=now_iso(),
        model="qwen3:8b",
    )
    store.create(stale)

    bundle = build_server()
    async with Client(bundle.server):
        pass  # entering/exiting the client drives the lifespan startup/shutdown

    reloaded = store.load(stale.job_id)
    assert reloaded is not None
    assert reloaded.state == "interrupted"
