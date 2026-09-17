"""Local setup and import operations. These are CLI-only, never remote MCP tools."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .config import Settings, config_path
from .evidence.manifest import IncidentManifest, ManifestFileEntry, SystemFacts, TimeWindow
from .evidence.paths import _reject_by_syntax
from .evidence.registry import load_files


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Replace JSON atomically, backing up existing bytes before any replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(f"{path.name}.bak-{uuid.uuid4().hex[:12]}"))
    temporary = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def desktop_config_path() -> Path:
    if sys.platform == "win32":
        return (
            Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming")))
            / "Claude/claude_desktop_config.json"
        )
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    raise ValueError("Specify --desktop-config on this platform, or use --no-desktop.")


def setup(
    *,
    data_dir: Path | None = None,
    model: str | None = None,
    fallback_model: str | None = None,
    desktop_config: Path | None = None,
    register_desktop: bool = True,
) -> dict[str, Any]:
    path = config_path()
    existing: dict[str, Any] = {}
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(existing, dict):
            raise ValueError("Saved configuration must be a JSON object; restore its backup.")
    defaults = Path.home() / "SAPIncidentLabData"
    values = dict(existing)
    if data_dir is not None or not existing:
        base = (data_dir or defaults).expanduser().resolve()
        values.update(root=str(base / "incidents"), output=str(base / "outputs"))
    if model is not None or "model" not in values:
        values["model"] = model or "qwen3.5:9b"
    if fallback_model is not None:
        values["fallback_model"] = fallback_model
    settings = Settings(**values)
    assert settings.root is not None and settings.output is not None
    # Validate overlap before making directories.
    root, output = settings.root.resolve(), settings.output.resolve()
    if root == output or root.is_relative_to(output) or output.is_relative_to(root):
        raise ValueError("Evidence and output folders must not contain each other.")
    config: dict[str, Any] = {}
    target = None
    if register_desktop:
        target = desktop_config or desktop_config_path()
        if target.exists():
            config = json.loads(target.read_text(encoding="utf-8-sig"))
        if not isinstance(config, dict) or not isinstance(config.get("mcpServers", {}), dict):
            raise ValueError(
                "Desktop configuration is invalid; restore a valid backup before setup."
            )
    root.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    if reason := settings.evidence_config_error():
        raise ValueError(reason)
    write_json(path, values)
    if target is not None:
        servers = config.setdefault("mcpServers", {})
        servers["sap-incident-lab"] = {
            "command": sys.executable,
            "args": ["-m", "sap_incident_lab", "--config", str(path), "serve"],
            "env": {
                "INCIDENT_LAB_CONFIG": str(path),
                "INCIDENT_LAB_ROOT": str(root),
                "INCIDENT_LAB_OUTPUT": str(output),
                "INCIDENT_LAB_MODEL": settings.model,
                **({"INCIDENT_LAB_FALLBACK_MODEL": settings.fallback_model} if settings.fallback_model else {}),
            },
        }
        write_json(target, config)
    return {
        "config": str(path),
        "root": str(root),
        "output": str(output),
        "model": settings.model,
        "fallback_model": settings.fallback_model,
        "desktop_config": str(target) if target else None,
        "next_steps": [
            "Run sap-incident-lab doctor.",
            "Run sap-incident-lab demo to add a synthetic incident.",
            *(
                [
                    "Fully quit and reopen Claude Desktop after registration.",
                    'Ask Claude: "Investigate INC-DEMO-001 and explain why the import failed."',
                ]
                if target is not None
                else [
                    "Configure your MCP client to run sap-incident-lab serve with this saved configuration.",
                ]
            ),
        ],
    }


def import_incident(
    settings: Settings,
    incident_id: str,
    sources: list[Path],
    *,
    summary: str = "",
    encoding: str = "utf-8",
    sid: str | None = None,
    timezone: str | None = None,
    classification: str = "unclassified",
) -> dict[str, Any]:
    """Copy explicitly selected files; never scan directories or overwrite an incident."""
    if reason := settings.evidence_config_error():
        raise ValueError(reason + ". Run sap-incident-lab setup first.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", incident_id):
        raise ValueError("Incident ID must contain 1–64 letters, digits, underscores or hyphens.")
    if not sources:
        raise ValueError("Select at least one exported text file.")
    assert settings.root is not None
    destination = settings.root / incident_id
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Incident {incident_id} already exists. Choose a new incident ID.")
    entries = []
    names: set[str] = set()
    for source in sources:
        _reject_by_syntax(source.name)
        name = source.name.casefold()
        if name in names or name == "incident.json" or name.startswith("evaluation-private"):
            raise ValueError(
                "Duplicate or reserved filename. Rename the selected export and retry."
            )
        names.add(name)
        if not source.is_file() or source.is_symlink():
            raise ValueError("Select regular exported files, not directories or symlinks.")
        entries.append(ManifestFileEntry(path=source.name, encoding=encoding, timezone=timezone))
    manifest = IncidentManifest(
        incident_id=incident_id,
        summary=summary,
        classification=classification,
        system=SystemFacts(sid=sid),
        time_window=TimeWindow(timezone=timezone),
        files=entries,
    )
    # Stage outside the evidence root, then validate the exact copied bytes before publishing.
    with tempfile.TemporaryDirectory(
        prefix="incident-import-", dir=settings.root.parent
    ) as temporary:
        staging_root = Path(temporary)
        staging = staging_root / incident_id
        staging.mkdir()
        for source in sources:
            with source.open("rb") as stream:
                raw = stream.read(settings.max_file_mb * 1024 * 1024 + 1)
            if len(raw) > settings.max_file_mb * 1024 * 1024:
                raise ValueError(f"{source.name} exceeds the {settings.max_file_mb} MB limit.")
            text = raw.decode(encoding)
            if "\x00" in text:
                raise ValueError(f"{source.name} contains NUL characters; select a text export.")
            (staging / source.name).write_bytes(raw)
        (staging / "incident.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        staged_settings = settings.model_copy(update={"root": staging_root})
        _, records = load_files(staged_settings, incident_id)
        # mkdir is exclusive even when a competing importer publishes the same ID.
        destination.mkdir()
        try:
            for child in staging.iterdir():
                shutil.copy2(child, destination / child.name)
        except BaseException:
            shutil.rmtree(destination)
            raise
    return {
        "incident_id": incident_id,
        "files_imported": len(records),
        "warnings": [warning for record in records for warning in record.warnings],
        "next_step": f'Ask Claude: "Investigate {incident_id} and explain what happened."',
    }


def install_demo(settings: Settings) -> dict[str, Any]:
    from importlib.resources import as_file, files

    with as_file(files("sap_incident_lab").joinpath("demo")) as folder:
        return import_incident(
            settings,
            "INC-DEMO-001",
            [folder / "import-log.txt", folder / "workprocess-trace.txt"],
            summary="Synthetic demo: transport import stalls on a stale enqueue lock.",
            classification="synthetic",
        )
