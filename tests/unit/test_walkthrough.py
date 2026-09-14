from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
from mcp import Client

from sap_incident_lab.config import get_settings
from sap_incident_lab.onboarding import install_demo, setup
from sap_incident_lab.server import build_server


async def test_setup_demo_investigate_resume_report(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "settings.json"
    desktop = tmp_path / "desktop.json"
    monkeypatch.setenv("INCIDENT_LAB_CONFIG", str(config))
    monkeypatch.setenv("INCIDENT_LAB_MAX_CHUNKS_PER_JOB", "1")
    setup(data_dir=tmp_path / "data", desktop_config=desktop)
    get_settings.cache_clear()
    settings = get_settings()
    install_demo(settings)
    calls = []
    real = httpx.AsyncClient

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "observations": [
                                {
                                    "id": "o1",
                                    "text": "Synthetic observation",
                                    "refs": [{"start_line": 1, "end_line": 1}],
                                }
                            ]
                        }
                    )
                }
            },
        )

    def patched(*args, **kwargs):
        return real(*args, **{**kwargs, "transport": httpx.MockTransport(handler)})

    monkeypatch.setattr("httpx.AsyncClient", patched)
    async with Client(build_server().server) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}
        assert {
            "incident_lab_investigate",
            "incident_lab_resume_analysis",
            "incident_lab_report_template",
        } <= names
        started = await client.call_tool(
            "incident_lab_investigate",
            {
                "incident_id": "INC-DEMO-001",
                "question": "Why did the import fail?",
            },
        )
        job_id = started.structured_content["job_id"]
        assert started.structured_content["files_selected"] == 2

        async def terminal():
            for _ in range(100):
                response = await client.call_tool("incident_lab_get_analysis", {"job_id": job_id})
                body = response.structured_content
                if body["state"] not in ("queued", "running", "cancelling"):
                    return body
                await asyncio.sleep(0.01)
            raise AssertionError("Job did not finish")

        partial = await terminal()
        assert partial["state"] == "partial"
        assert partial["progress"]["can_resume"]
        await client.call_tool("incident_lab_resume_analysis", {"job_id": job_id})
        completed = await terminal()
        assert completed["state"] == "completed"
        assert completed["progress"]["coverage_percent"] == 100
        assert len(calls) == 2
        outcome = completed["results"][0]
        evidence = await client.call_tool(
            "incident_lab_get_evidence",
            {
                "incident_id": "INC-DEMO-001",
                "file_id": outcome["file_id"],
                "start_line": 1,
                "end_line": 1,
                "expected_sha256": outcome["sha256"],
            },
        )
        assert evidence.structured_content["lines"]
        template = await client.call_tool(
            "incident_lab_report_template",
            {
                "incident_id": "INC-DEMO-001",
                "job_ids": [job_id],
            },
        )
        markdown = template.structured_content["markdown"]
        for section in (
            "Findings and evidence",
            "Hypotheses",
            "Missing information",
            "Next checks",
            "Limitations",
        ):
            assert "## " + section in markdown
        assert "2 of 2 chunks completed" in markdown
        saved = await client.call_tool(
            "incident_lab_save_report",
            {
                "incident_id": "INC-DEMO-001",
                "job_ids": [job_id],
                "markdown": markdown,
            },
        )
        assert (settings.output / saved.structured_content["path"]).is_file()
    get_settings.cache_clear()


def test_cli_setup_demo_and_import_from_another_directory(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    desktop = tmp_path / "desktop.json"
    env = {k: v for k, v in os.environ.items() if not k.startswith("INCIDENT_LAB_")}

    def run(*args):
        return subprocess.run(
            [sys.executable, "-m", "sap_incident_lab", "--config", str(config), *args],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=20,
        )

    configured = run(
        "setup", "--data-dir", str(tmp_path / "data"), "--desktop-config", str(desktop)
    )
    assert configured.returncode == 0, configured.stderr
    demo = run("demo", "--json")
    assert demo.returncode == 0, demo.stderr
    assert json.loads(demo.stdout)["files_imported"] == 2
    source = tmp_path / "new log.txt"
    source.write_text("exported evidence\n")
    imported = run("import", "INC-NEW", str(source), "--json")
    assert imported.returncode == 0, imported.stderr
    assert json.loads(imported.stdout)["incident_id"] == "INC-NEW"
    failed = run("import", "INC-NEW", str(source))
    assert failed.returncode == 1
    assert "already exists" in failed.stderr
    assert "Traceback" not in failed.stderr
