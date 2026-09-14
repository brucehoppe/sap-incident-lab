from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import errors
from ..config import Settings
from .manifest import IncidentManifest, ManifestError, ManifestFileEntry, load_manifest
from .paths import PathRejected, resolve_evidence_path, resolve_incident_dir

_INCIDENT_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


@dataclass(slots=True)
class FileRecord:
    """A file as actually read from disk: identity, bytes, and decoded lines.

    Always rebuilt from the current bytes on disk (see get_file) rather than
    cached, so a get_evidence call can never return lines that no longer
    match the file's current sha256 — the mismatch surfaces as SOURCE_CHANGED
    instead (DESIGN.md section 7).
    """

    file_id: str
    rel_path: str
    encoding: str
    declared_timezone: str | None
    sha256: str
    size_bytes: int
    line_count: int
    lines: list[str]
    warnings: list[str]


def _file_id(index: int) -> str:
    return f"f{index + 1:02d}"


def list_incidents(settings: Settings) -> list[str]:
    config_error = settings.evidence_config_error()
    if config_error:
        raise errors.config_invalid(config_error)
    assert settings.root is not None
    found: list[str] = []
    for entry in sorted(settings.root.iterdir()):
        if not entry.is_dir() or not (entry / "incident.json").is_file():
            continue
        try:
            _incident_dir, manifest = _load_manifest_for(settings, entry.name)
        except errors.ToolError:
            continue
        if manifest.incident_id == entry.name:
            found.append(entry.name)
    return found


def _load_manifest_for(settings: Settings, incident_id: str) -> tuple[Path, IncidentManifest]:
    config_error = settings.evidence_config_error()
    if config_error:
        raise errors.config_invalid(config_error)
    assert settings.root is not None
    if not _INCIDENT_ID_RE.fullmatch(incident_id):
        raise errors.incident_not_found(incident_id)
    try:
        incident_dir = resolve_incident_dir(settings.root, incident_id)
    except PathRejected as exc:
        raise errors.incident_not_found(incident_id) from exc
    try:
        manifest = load_manifest(incident_dir)
    except ManifestError as exc:
        raise errors.manifest_invalid(incident_id, str(exc)) from exc
    if manifest.incident_id != incident_id:
        raise errors.manifest_invalid(
            incident_id, f"incident.json declares '{manifest.incident_id}'"
        )
    return incident_dir, manifest


def _read_one(
    settings: Settings,
    incident_id: str,
    entry: ManifestFileEntry,
    file_id: str,
) -> FileRecord:
    assert settings.root is not None
    try:
        resolved = resolve_evidence_path(settings.root, incident_id, entry.path)
    except PathRejected as exc:
        raise errors.path_rejected(file_id) from exc

    size_bytes = resolved.stat().st_size
    max_bytes = settings.max_file_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise errors.file_too_large(file_id, settings.max_file_mb)

    # One read of the raw bytes: the hash and the decoded text always agree,
    # with no reopen between them for the file to change under (DESIGN.md
    # section 7, "compute SHA-256 from raw bytes ... no check-then-reopen").
    with resolved.open("rb") as source:
        raw = source.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise errors.file_too_large(file_id, settings.max_file_mb)
    size_bytes = len(raw)
    sha256 = hashlib.sha256(raw).hexdigest()

    # utf-8-sig strips a BOM if present and is otherwise identical to utf-8,
    # so the BOM never becomes a stray character in line 1 — but it is still
    # part of `raw`, so it is still part of the hash.
    decode_encoding = "utf-8-sig" if entry.encoding.lower() in ("utf-8", "utf8") else entry.encoding
    try:
        text = raw.decode(decode_encoding)
    except (LookupError, UnicodeDecodeError) as exc:
        raise errors.decode_failed(file_id, entry.encoding) from exc

    lines = text.splitlines()  # preserves blank lines; handles CRLF and LF
    warnings = [
        f"line {i + 1} exceeds max_chunk_chars ({settings.max_chunk_chars}) "
        "and will be reported as oversize during analysis"
        for i, line in enumerate(lines)
        if len(line) > settings.max_chunk_chars
    ]

    return FileRecord(
        file_id=file_id,
        rel_path=entry.path,
        encoding=entry.encoding,
        declared_timezone=entry.timezone,
        sha256=sha256,
        size_bytes=size_bytes,
        line_count=len(lines),
        lines=lines,
        warnings=warnings,
    )


def load_files(settings: Settings, incident_id: str) -> tuple[IncidentManifest, list[FileRecord]]:
    _incident_dir, manifest = _load_manifest_for(settings, incident_id)
    records = [
        _read_one(settings, incident_id, entry, _file_id(i))
        for i, entry in enumerate(manifest.files)
    ]
    return manifest, records


def get_file(settings: Settings, incident_id: str, file_id: str) -> FileRecord:
    _manifest, records = load_files(settings, incident_id)
    for record in records:
        if record.file_id == file_id:
            return record
    raise errors.file_not_found(incident_id, file_id)


def describe_files(manifest: IncidentManifest, records: list[FileRecord]) -> dict[str, Any]:
    return {
        "incident_id": manifest.incident_id,
        "summary": manifest.summary,
        "system": manifest.system.model_dump(),
        "time_window": manifest.time_window.model_dump(),
        "files": [
            {
                "file_id": r.file_id,
                "path": r.rel_path,
                "encoding": r.encoding,
                "timezone": r.declared_timezone,
                "sha256": r.sha256,
                "size_bytes": r.size_bytes,
                "line_count": r.line_count,
                "warnings": r.warnings,
            }
            for r in records
        ],
    }


def read_evidence_window(
    settings: Settings,
    incident_id: str,
    file_id: str,
    start_line: int,
    end_line: int,
    expected_sha256: str | None,
) -> dict[str, Any]:
    record = get_file(settings, incident_id, file_id)

    if expected_sha256 is not None and expected_sha256 != record.sha256:
        raise errors.source_changed(file_id)

    if start_line < 1 or end_line < start_line or start_line > record.line_count:
        raise errors.range_invalid(file_id, start_line, end_line)

    end_line = min(end_line, record.line_count)

    lines: list[dict[str, Any]] = []
    total_chars = 0
    clipped = False
    next_start_line: int | None = None
    for lineno in range(start_line, end_line + 1):
        text = record.lines[lineno - 1]
        over_lines = len(lines) >= settings.evidence_max_lines
        over_chars = total_chars + len(text) > settings.evidence_max_chars
        if over_lines or over_chars:
            clipped = True
            next_start_line = lineno
            break
        lines.append({"line": lineno, "text": text})
        total_chars += len(text)

    return {
        "incident_id": incident_id,
        "file_id": file_id,
        "sha256": record.sha256,
        "requested_range": {"start_line": start_line, "end_line": end_line},
        "lines": lines,
        "clipped": clipped,
        "next_start_line": next_start_line,
    }


def search_evidence(
    settings: Settings,
    incident_id: str,
    query: str,
    file_ids: list[str] | None = None,
    case_sensitive: bool = False,
    max_results: int = 50,
) -> dict[str, Any]:
    """Find literal text in registered evidence and return citation-ready lines."""
    if not query.strip() or len(query) > 2000:
        raise errors.ToolError(
            "QUERY_INVALID", "Provide a search query of 1–2000 characters.",
            "Supply a focused literal term or phrase.",
        )
    if max_results < 1 or max_results > 100:
        raise errors.ToolError(
            "LIMIT_INVALID", "max_results must be between 1 and 100.",
            "Use a smaller result limit and refine the query if needed.",
        )
    _manifest, records = load_files(settings, incident_id)
    selected = records if file_ids is None else [r for r in records if r.file_id in file_ids]
    unknown = sorted(set(file_ids or []) - {r.file_id for r in records})
    if unknown:
        raise errors.file_not_found(incident_id, unknown[0])
    needle = query if case_sensitive else query.casefold()
    matches: list[dict[str, Any]] = []
    for record in selected:
        for line_number, text in enumerate(record.lines, start=1):
            haystack = text if case_sensitive else text.casefold()
            if needle in haystack:
                matches.append({
                    "file_id": record.file_id,
                    "path": record.rel_path,
                    "line": line_number,
                    "text": text,
                    "sha256": record.sha256,
                })
                if len(matches) >= max_results:
                    return {
                        "incident_id": incident_id, "query": query,
                        "case_sensitive": case_sensitive, "matches": matches,
                        "truncated": True, "next_step": "Refine the query or pass a higher max_results.",
                    }
    return {
        "incident_id": incident_id, "query": query,
        "case_sensitive": case_sensitive, "matches": matches,
        "truncated": False,
    }
