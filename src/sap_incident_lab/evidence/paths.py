from __future__ import annotations

from pathlib import Path, PureWindowsPath


class PathRejected(Exception):
    """A manifest path failed containment checks. Never includes the
    resolved absolute path in its message — see errors.path_rejected."""


def _reject_by_syntax(rel: str) -> None:
    """Reject a manifest-declared relative path on syntax alone, before any
    filesystem access. Catches cases `Path.resolve()` alone would not: a
    Windows drive letter or UNC root, or an alternate-data-stream colon, is a
    perfectly normal-looking relative path on this Mac and only misbehaves on
    Windows — so it is rejected here unconditionally rather than only when
    running on Windows (DESIGN.md section 7: "Test these on Windows", but the
    check itself must not be platform-conditional).
    """
    if not rel or "\x00" in rel:
        raise PathRejected("empty or contains a NUL byte")
    if rel.startswith("/") or rel.startswith("\\"):
        raise PathRejected("must be relative")
    pure = PureWindowsPath(rel)
    if pure.drive or pure.root:
        raise PathRejected("must not contain a drive letter or UNC root")
    if ".." in pure.parts:
        raise PathRejected("must not contain '..'")
    if ":" in rel:
        # Blocks both a bare drive letter (already caught above) and the
        # Windows alternate-data-stream form `file.txt:stream`.
        raise PathRejected("must not contain ':'")


def resolve_evidence_path(root: Path, incident_id: str, rel_path: str) -> Path:
    """Resolve a manifest-declared relative path to a real file, or raise
    PathRejected. Symlinks and junctions are resolved (`resolve(strict=True)`)
    before the containment check, so a symlink that leads outside the
    incident directory is rejected rather than silently followed.
    """
    _reject_by_syntax(rel_path)

    incident_dir = resolve_incident_dir(root, incident_id)
    try:
        candidate = (incident_dir / rel_path).resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise PathRejected("does not exist") from exc
    if not candidate.is_relative_to(incident_dir):
        raise PathRejected("resolves outside the incident directory")
    if not candidate.is_file():
        raise PathRejected("is not a regular file")
    return candidate


def resolve_incident_dir(root: Path, incident_id: str) -> Path:
    try:
        root_resolved = root.resolve(strict=True)
        incident_dir = (root_resolved / incident_id).resolve(strict=True)
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise PathRejected("does not exist") from exc
    if not incident_dir.is_relative_to(root_resolved):
        raise PathRejected("incident directory escapes the configured root")
    if not incident_dir.is_dir():
        raise PathRejected("is not a directory")
    return incident_dir
