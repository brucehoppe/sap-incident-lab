from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from ..analysis.schemas import PROMPT_VERSION, ChunkOutcome

JobState = Literal[
    "queued",
    "running",
    "cancelling",
    "completed",
    "partial",
    "failed",
    "cancelled",
    "interrupted",
]

# States that mean "something is or was expected to still be working on this
# job in this process." Any job store still in one of these when the server
# starts belongs to a process that no longer exists (DESIGN.md section 9:
# "on restart, mark unfinished running jobs interrupted").
_LIVE_STATES: frozenset[JobState] = frozenset({"queued", "running", "cancelling"})


class JobRecord(BaseModel):
    job_id: str
    incident_id: str
    file_ids: list[str]
    question: str
    state: JobState
    created_at: str
    started_at: str | None = None
    ended_at: str | None = None
    model: str
    prompt_version: str = PROMPT_VERSION
    accepted_chunk_ids: list[str] = Field(default_factory=list)
    processed_chunk_ids: list[str] = Field(default_factory=list)
    skipped_chunk_ids: list[str] = Field(default_factory=list)  # oversize, never sent to the model
    unprocessed_chunk_ids: list[str] = Field(default_factory=list)  # over budget, or cut short
    error: str | None = None


def new_job_id(incident_id: str) -> str:
    return f"{incident_id}-{uuid.uuid4().hex[:8]}"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write via a temp file + os.replace so a crash mid-write never leaves a
    half-written job/chunk file (DESIGN.md section 9: "atomic replacement").
    os.replace is atomic on both macOS and Windows, unlike a plain rename
    over an existing file on Windows.
    """
    tmp_path = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


class JobStore:
    def __init__(self, output_root: Path) -> None:
        self.jobs_dir = output_root / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def _job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / job_id

    def _job_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "job.json"

    def _chunks_dir(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "chunks"

    def create(self, job: JobRecord) -> None:
        self._job_dir(job.job_id).mkdir(parents=True, exist_ok=True)
        self._chunks_dir(job.job_id).mkdir(parents=True, exist_ok=True)
        _atomic_write_json(self._job_path(job.job_id), job.model_dump())

    def save(self, job: JobRecord) -> None:
        _atomic_write_json(self._job_path(job.job_id), job.model_dump())

    def load(self, job_id: str) -> JobRecord | None:
        path = self._job_path(job_id)
        if not path.is_file():
            return None
        return JobRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def save_chunk_result(self, job_id: str, outcome: ChunkOutcome) -> None:
        safe_name = outcome.chunk_id.replace("/", "_").replace(":", "_")
        path = self._chunks_dir(job_id) / f"{safe_name}.json"
        _atomic_write_json(path, outcome.model_dump())

    def list_chunk_results(self, job_id: str) -> list[ChunkOutcome]:
        chunks_dir = self._chunks_dir(job_id)
        if not chunks_dir.is_dir():
            return []
        results = [
            ChunkOutcome.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(chunks_dir.glob("*.json"))
        ]
        results.sort(key=lambda c: (c.file_id, c.start_line))
        return results

    def list_job_ids(self) -> list[str]:
        if not self.jobs_dir.is_dir():
            return []
        return sorted(p.name for p in self.jobs_dir.iterdir() if p.is_dir())

    def recover_interrupted_jobs(self) -> list[str]:
        """Mark every job left in a 'live' state as interrupted. Called once
        at server startup, before any tool can create a new job, so a stale
        'running' record from a killed process can never block or be
        confused with real progress (DESIGN.md section 9)."""
        recovered: list[str] = []
        for job_id in self.list_job_ids():
            job = self.load(job_id)
            if job is None or job.state not in _LIVE_STATES:
                continue
            job.state = "interrupted"
            job.ended_at = now_iso()
            self.save(job)
            recovered.append(job_id)
        return recovered

    def find_live_job(self) -> str | None:
        """Return the job_id of any job still queued/running/cancelling, so
        start_analysis can refuse a second concurrent job (DESIGN.md section
        9: "keep one local inference job active at a time")."""
        for job_id in self.list_job_ids():
            job = self.load(job_id)
            if job is not None and job.state in _LIVE_STATES:
                return job_id
        return None
