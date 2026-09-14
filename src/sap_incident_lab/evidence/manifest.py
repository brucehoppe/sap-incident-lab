from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError


class SystemFacts(BaseModel):
    sid: str | None = None
    product: str | None = None
    release: str | None = None
    kernel: str | None = None
    database: str | None = None


class TimeWindow(BaseModel):
    start: str | None = None
    end: str | None = None
    timezone: str | None = None


class ManifestFileEntry(BaseModel):
    """One evidence file as declared in incident.json.

    `path` is relative to the incident directory and is validated for
    containment separately (see paths.py) — this model only shapes the data,
    it does not touch the filesystem.
    """

    path: str
    encoding: str = "utf-8"
    timezone: str | None = None


class IncidentManifest(BaseModel):
    incident_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    summary: str = ""
    system: SystemFacts = Field(default_factory=SystemFacts)
    time_window: TimeWindow = Field(default_factory=TimeWindow)
    files: list[ManifestFileEntry] = Field(default_factory=list)


class ManifestError(Exception):
    """Raised when incident.json is missing or fails validation; callers turn
    this into a ToolError (MANIFEST_INVALID / INCIDENT_NOT_FOUND)."""


def load_manifest(incident_dir: Path) -> IncidentManifest:
    manifest_path = incident_dir / "incident.json"
    if not manifest_path.resolve().is_relative_to(incident_dir.resolve()):
        raise ManifestError("incident.json resolves outside the incident directory")
    if not manifest_path.is_file():
        raise ManifestError(f"no incident.json in {incident_dir.name}")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestError("incident.json is not valid JSON or could not be read as UTF-8") from exc
    try:
        return IncidentManifest.model_validate(raw)
    except ValidationError as exc:
        raise ManifestError(f"incident.json failed validation: {exc}") from exc
