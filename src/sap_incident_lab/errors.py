from __future__ import annotations

from typing import Any


class ToolError(Exception):
    """A stable, structured error a tool returns to Claude.

    Never carries an absolute path or trace text (secure defaults: error
    messages must not leak internal detail — see docs/implementation-guide.md
    section 8 and DESIGN.md section 3). `message` is a short human sentence;
    `recovery` tells Claude what to do next; `code` is meant to be matched on.
    """

    def __init__(self, code: str, message: str, recovery: str, **extra: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.recovery = recovery
        self.extra = extra

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "recovery": self.recovery,
                **self.extra,
            }
        }


def config_invalid(reason: str) -> ToolError:
    return ToolError(
        "CONFIG_INVALID",
        f"Server configuration is incomplete: {reason}.",
        "Set INCIDENT_LAB_ROOT and INCIDENT_LAB_OUTPUT in the Desktop config and restart.",
    )


def incident_not_found(incident_id: str) -> ToolError:
    return ToolError(
        "INCIDENT_NOT_FOUND",
        f"No incident '{incident_id}' with a valid manifest was found.",
        "Call incident_lab_list_incidents to see available incident IDs.",
    )


def manifest_invalid(incident_id: str, reason: str) -> ToolError:
    return ToolError(
        "MANIFEST_INVALID",
        f"incident.json for '{incident_id}' is invalid: {reason}.",
        "Fix the manifest on disk, then retry.",
    )


def file_not_found(incident_id: str, file_id: str) -> ToolError:
    return ToolError(
        "FILE_NOT_FOUND",
        f"File '{file_id}' is not registered for incident '{incident_id}'.",
        "Call incident_lab_list_files to see valid file IDs.",
    )


def path_rejected(file_id: str) -> ToolError:
    return ToolError(
        "PATH_REJECTED",
        f"File '{file_id}' resolves outside the incident's evidence directory.",
        "This file cannot be served; check the manifest for a path error.",
    )


def file_too_large(file_id: str, max_mb: int) -> ToolError:
    return ToolError(
        "FILE_TOO_LARGE",
        f"File '{file_id}' exceeds the {max_mb} MB limit.",
        "Export a smaller excerpt of this file.",
    )


def decode_failed(file_id: str, encoding: str) -> ToolError:
    return ToolError(
        "DECODE_FAILED",
        f"File '{file_id}' could not be decoded as {encoding}.",
        "Correct the declared encoding in incident.json and retry.",
    )


def range_invalid(file_id: str, start_line: int, end_line: int) -> ToolError:
    return ToolError(
        "RANGE_INVALID",
        f"Requested range {start_line}-{end_line} is invalid for file '{file_id}'.",
        "Use a 1-based range within the file's line count.",
    )


def source_changed(file_id: str) -> ToolError:
    return ToolError(
        "SOURCE_CHANGED",
        f"File '{file_id}' has changed since it was last inventoried.",
        "Call incident_lab_list_files again and restart analysis with fresh hashes.",
    )


def job_not_found(job_id: str) -> ToolError:
    return ToolError(
        "JOB_NOT_FOUND",
        f"No analysis job '{job_id}' was found.",
        "Call incident_lab_start_analysis to create one.",
    )


def job_busy(running_job_id: str) -> ToolError:
    return ToolError(
        "JOB_BUSY",
        f"Job '{running_job_id}' is already running; only one analysis runs at a time.",
        "Wait and call incident_lab_get_analysis, or cancel the running job first.",
    )


def ollama_unavailable(detail: str) -> ToolError:
    return ToolError(
        "OLLAMA_UNAVAILABLE",
        f"Local Ollama endpoint is unreachable: {detail}.",
        "Start Ollama and call incident_lab_health to confirm.",
    )


def model_missing(model: str) -> ToolError:
    return ToolError(
        "MODEL_MISSING",
        f"Model '{model}' is not installed in Ollama.",
        f"Run `ollama pull {model}` and retry.",
    )
