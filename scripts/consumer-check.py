"""Install a wheel into a fresh venv and exercise setup/demo plus real stdio MCP.

Run with: uv run python scripts/consumer-check.py dist/package.whl
Add --offline when the locked dependencies are already in uv's cache.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CHECK = """
import asyncio
import json
from pathlib import Path
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from sap_incident_lab.analysis.ollama_client import load_system_prompt
import sap_incident_lab
assert Path(sap_incident_lab.__file__).resolve().is_relative_to(Path.cwd() / "venv")
assert len(load_system_prompt()) > 100
entry = json.loads(Path("desktop.json").read_text())["mcpServers"]["sap-incident-lab"]
async def check():
    async with Client(StdioServerParameters(**entry)) as client:
        listing = await client.call_tool("incident_lab_list_incidents", {})
        assert listing.structured_content["incident_ids"] == ["INC-DEMO-001"]
        inventory = await client.call_tool("incident_lab_list_files", {"incident_id": "INC-DEMO-001"})
        assert len(inventory.structured_content["files"]) == 2
        template = await client.call_tool("incident_lab_report_template", {"incident_id": "INC-DEMO-001", "job_ids": []})
        assert "## Findings and evidence" in template.structured_content["markdown"]
asyncio.run(check())
print("PASS: fresh wheel install, packaged prompt/demo, setup, and Desktop command stdio MCP handshake.")
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    repository = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="incident-consumer-") as directory:
        root = Path(directory).resolve()
        offline = ["--offline"] if args.offline else []
        requirements = root / "requirements.txt"
        subprocess.run(
            [
                "uv",
                "export",
                "--locked",
                "--no-dev",
                "--no-hashes",
                "--no-emit-project",
                "--output-file",
                str(requirements),
                *offline,
            ],
            cwd=repository,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            ["uv", "venv", "--python", sys.executable, str(root / "venv"), *offline], check=True
        )
        python = root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "-r",
                str(requirements),
                str(wheel),
                *offline,
            ],
            check=True,
        )
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("INCIDENT_LAB_") and key not in ("PYTHONPATH", "PYTHONHOME")
        }
        config = root / "config.json"
        common = [str(python), "-m", "sap_incident_lab", "--config", str(config)]
        subprocess.run(
            [
                *common,
                "setup",
                "--data-dir",
                str(root / "data"),
                "--desktop-config",
                str(root / "desktop.json"),
            ],
            cwd=root,
            env=env,
            check=True,
        )
        subprocess.run([*common, "demo"], cwd=root, env=env, check=True)
        # A second setup must preserve the installed demo and the chosen configuration.
        subprocess.run(
            [*common, "setup", "--desktop-config", str(root / "desktop.json")],
            cwd=root,
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        env["INCIDENT_LAB_CONFIG"] = str(config)
        subprocess.run([str(python), "-c", CHECK], cwd=root, env=env, check=True)
        assert json.loads(config.read_text())["root"] == str(root / "data/incidents")


if __name__ == "__main__":
    main()
