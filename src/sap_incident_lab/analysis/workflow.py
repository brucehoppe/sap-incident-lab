from __future__ import annotations

from typing import Any

from .. import errors
from ..config import Settings
from ..evidence.registry import load_files
from ..jobs.store import JobRecord, JobStore, PlannedChunk, new_job_id, now_iso
from .chunking import Chunk
from .schemas import PROMPT_VERSION
from .worker import RangeRequest, plan_chunks


def create_analysis(
    settings: Settings,
    store: JobStore,
    incident_id: str,
    file_ids: list[str],
    question: str,
    ranges: list[RangeRequest] | None = None,
) -> tuple[JobRecord, list[Chunk]]:
    if not question.strip() or len(question) > 4000:
        raise errors.ToolError(
            "QUESTION_INVALID",
            "Provide a question of 1–4000 characters.",
            "Ask one focused incident question.",
        )
    if busy := store.find_live_job():
        raise errors.job_busy(busy)
    chunks, hashes = plan_chunks(settings, incident_id, file_ids, ranges)
    accepted = chunks[: settings.max_chunks_per_job]
    job = JobRecord(
        job_id=new_job_id(incident_id),
        incident_id=incident_id,
        file_ids=file_ids,
        question=question,
        state="queued",
        created_at=now_iso(),
        model=settings.model,
        accepted_chunk_ids=[c.chunk_id for c in accepted],
        unprocessed_chunk_ids=[c.chunk_id for c in chunks[len(accepted) :]],
        file_hashes=hashes,
        plan=[
            PlannedChunk(
                chunk_id=c.chunk_id,
                file_id=c.file_id,
                start_line=c.start_line,
                end_line=c.end_line,
                oversize=c.oversize,
            )
            for c in chunks
        ],
    )
    store.create(job)
    return job, accepted


def resume_analysis(
    settings: Settings, store: JobStore, job_id: str
) -> tuple[JobRecord, list[Chunk]]:
    if busy := store.find_live_job():
        raise errors.job_busy(busy)
    job = store.load(job_id)
    if job is None:
        raise errors.job_not_found(job_id)
    if not job.plan or not job.file_hashes:
        raise errors.ToolError(
            "RESUME_UNAVAILABLE",
            "This older job has no saved chunk plan.",
            "Start a new investigation.",
        )
    if job.model != settings.model or job.prompt_version != PROMPT_VERSION:
        raise errors.ToolError(
            "RESUME_CONFIG_CHANGED",
            "The model or prompt version changed.",
            "Restore the original configuration or start a new investigation.",
        )
    _, records = load_files(settings, job.incident_id)
    by_id = {record.file_id: record for record in records}
    for file_id, sha256 in job.file_hashes.items():
        if file_id not in by_id or by_id[file_id].sha256 != sha256:
            raise errors.source_changed(file_id)
    remaining = [
        c
        for c in job.plan
        if c.chunk_id not in job.processed_chunk_ids and c.chunk_id not in job.skipped_chunk_ids
    ]
    if not remaining:
        raise errors.ToolError(
            "NOTHING_TO_RESUME",
            "There are no retryable chunks remaining.",
            "Review the results; oversize lines require smaller exported excerpts.",
        )
    selected = remaining[: settings.max_chunks_per_job]
    chunks = [
        Chunk(
            chunk_id=c.chunk_id,
            file_id=c.file_id,
            start_line=c.start_line,
            end_line=c.end_line,
            lines=by_id[c.file_id].lines[c.start_line - 1 : c.end_line],
            oversize=c.oversize,
        )
        for c in selected
    ]
    # Nothing is mutated until all source hashes and the saved scope pass validation.
    job.state = "queued"
    job.error = None
    job.ended_at = None
    job.attempts += 1
    job.accepted_chunk_ids = list(
        dict.fromkeys(job.accepted_chunk_ids + [c.chunk_id for c in selected])
    )
    job.unprocessed_chunk_ids = [c.chunk_id for c in remaining]
    store.save(job)
    return job, chunks


def progress(store: JobStore, job: JobRecord) -> dict[str, Any]:
    outcomes = store.list_chunk_results(job.job_id)
    planned = {c.chunk_id for c in job.plan} or (
        set(job.accepted_chunk_ids) | set(job.unprocessed_chunk_ids)
    )
    completed = set(job.processed_chunk_ids)
    skipped = set(job.skipped_chunk_ids)
    remaining = planned - completed - skipped
    failed = {
        r.chunk_id for r in outcomes if r.status in ("invalid_output", "truncated_output")
    } & remaining
    active = job.state in ("queued", "running", "cancelling")
    can_resume = bool(remaining and job.plan and not active)
    if active:
        next_step = "Poll incident_lab_get_analysis for progress and results."
    elif can_resume:
        next_step = (
            "Call incident_lab_resume_analysis to retry failures and continue remaining chunks."
        )
    elif skipped:
        next_step = "Export shorter lines for oversize evidence, then start a new investigation."
    elif not job.plan and remaining:
        next_step = "Start a new investigation; this older job has no resumable plan."
    else:
        next_step = "Verify findings with incident_lab_get_evidence, then request incident_lab_report_template."
    total = len(planned)
    return {
        "total_chunks": total,
        "completed_chunks": len(completed),
        "failed_chunks": len(failed),
        "remaining_chunks": len(remaining),
        "pending_chunks": len(remaining - failed),
        "skipped_chunks": len(skipped),
        "coverage_percent": round(100 * len(completed) / total, 1) if total else 0.0,
        "attempts": job.attempts,
        "can_resume": can_resume,
        "summary": f"{len(completed)} of {total} chunks completed; {len(failed)} failed, {len(remaining - failed)} pending, {len(skipped)} skipped.",
        "next_step": next_step,
    }
