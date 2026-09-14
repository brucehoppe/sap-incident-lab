from __future__ import annotations

import asyncio

import structlog

from .. import errors
from ..config import Settings
from ..evidence.registry import get_file
from ..jobs.store import JobStore, now_iso
from .chunking import Chunk, chunk_lines
from .ollama_client import extract_with_repair
from .schemas import ChunkOutcome
from .validate import clip_invalid_refs

_LOG = structlog.get_logger(__name__)


class RangeRequest:
    __slots__ = ("file_id", "start_line", "end_line")

    def __init__(self, file_id: str, start_line: int, end_line: int) -> None:
        self.file_id = file_id
        self.start_line = start_line
        self.end_line = end_line


def plan_chunks(
    settings: Settings,
    incident_id: str,
    file_ids: list[str],
    ranges: list[RangeRequest] | None,
) -> tuple[list[Chunk], dict[str, str]]:
    """Resolve file_ids/ranges into a deterministic, ordered chunk plan, plus
    a {file_id: sha256} map captured once at planning time. The evidence is
    exported and static (guide section 1: "the original files remain
    unchanged"), so this snapshot is what the job analyzes even if start_line
    analysis takes a while — a live re-check on every chunk would only catch
    a case this project explicitly does not target (a changing source file).
    incident_lab_get_evidence remains the tool that always re-reads current
    bytes, for when a claim needs verifying against the live file.
    """
    file_hashes: dict[str, str] = {}
    all_chunks: list[Chunk] = []
    requests = ranges or [
        RangeRequest(file_id, 1, get_file(settings, incident_id, file_id).line_count)
        for file_id in file_ids
    ]
    for req in requests:
        record = get_file(settings, incident_id, req.file_id)
        file_hashes[req.file_id] = record.sha256
        if req.start_line < 1 or req.end_line < req.start_line or req.end_line > record.line_count:
            raise errors.range_invalid(req.file_id, req.start_line, req.end_line)
        chunks = chunk_lines(
            req.file_id,
            record.lines,
            start_line=req.start_line,
            end_line=req.end_line,
            max_lines=settings.max_chunk_lines,
            max_chars=settings.max_chunk_chars,
            overlap_lines=settings.chunk_overlap_lines,
        )
        all_chunks.extend(chunks)
    return all_chunks, file_hashes


async def run_job(
    settings: Settings,
    store: JobStore,
    job_id: str,
    chunks: list[Chunk],
    file_hashes: dict[str, str],
    question: str,
    cancel_event: asyncio.Event,
) -> None:
    """Process a job's accepted chunks sequentially, persisting each result
    immediately (guide section 9.1: "persist each successful result
    immediately"). Runs as a fire-and-forget asyncio task created by the
    start_analysis tool — see server.py — so the tool call itself returns
    promptly regardless of how long the whole job takes.
    """
    job = store.load(job_id)
    assert job is not None
    job.state = "running"
    job.started_at = now_iso()
    store.save(job)

    processed: list[str] = []
    failed_statuses: list[str] = []
    cancelled_mid_run = False
    stopped_early_error: str | None = None

    for chunk in chunks:
        if cancel_event.is_set():
            cancelled_mid_run = True
            break

        if chunk.oversize:
            outcome = ChunkOutcome(
                job_id=job_id,
                chunk_id=chunk.chunk_id,
                file_id=chunk.file_id,
                sha256=file_hashes[chunk.file_id],
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                status="oversize_skipped",
                model=settings.model,
            )
            store.save_chunk_result(job_id, outcome)
            job.skipped_chunk_ids.append(chunk.chunk_id)
            store.save(job)
            continue

        try:
            result, repaired = await extract_with_repair(
                settings,
                question=question,
                file_id=chunk.file_id,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                lines=chunk.lines,
            )
        except errors.ToolError as exc:
            # Ollama itself is unreachable (not a bad response — that comes
            # back as a status, see ollama_client.extract_once). Every
            # remaining chunk would fail identically, so stop rather than
            # burn the chunk budget on calls certain to fail the same way;
            # this must not propagate further, or it kills the background
            # task silently and leaves the job stuck in "running" forever.
            stopped_early_error = exc.message
            _LOG.warning("job_stopped_by_ollama_error", job_id=job_id, code=exc.code)
            break

        extraction = result.extraction
        dropped = 0
        if extraction is not None:
            extraction, dropped = clip_invalid_refs(extraction, chunk.start_line, chunk.end_line)

        outcome = ChunkOutcome(
            job_id=job_id,
            chunk_id=chunk.chunk_id,
            file_id=chunk.file_id,
            sha256=file_hashes[chunk.file_id],
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            status=result.status,
            extraction=extraction,
            invalid_refs_dropped=dropped,
            model=settings.model,
            elapsed_seconds=result.elapsed_seconds,
            repair_attempted=repaired,
        )
        store.save_chunk_result(job_id, outcome)

        if result.status == "completed":
            processed.append(chunk.chunk_id)
        else:
            failed_statuses.append(chunk.chunk_id)
        job.processed_chunk_ids = processed
        store.save(job)

        _LOG.info(
            "chunk_processed",
            job_id=job_id,
            chunk_id=chunk.chunk_id,
            status=result.status,
            elapsed_seconds=round(result.elapsed_seconds, 2),
        )

    job = store.load(job_id)
    assert job is not None
    job.ended_at = now_iso()

    def _mark_remaining_unprocessed() -> None:
        remaining = [c.chunk_id for c in chunks if c.chunk_id not in job.processed_chunk_ids
                     and c.chunk_id not in job.skipped_chunk_ids]
        job.unprocessed_chunk_ids = sorted(set(job.unprocessed_chunk_ids) | set(remaining))

    if stopped_early_error is not None:
        _mark_remaining_unprocessed()
        job.state = "failed" if not processed else "partial"
        job.error = stopped_early_error
    elif cancelled_mid_run or cancel_event.is_set():
        _mark_remaining_unprocessed()
        job.state = "cancelled"
    elif not processed and not job.skipped_chunk_ids:
        job.state = "failed"
        job.error = "no chunk produced usable output"
    elif job.unprocessed_chunk_ids or failed_statuses or job.skipped_chunk_ids:
        # An oversize-skipped chunk is real, disclosed missing coverage, not
        # a clean result — a job is only 'completed' when every accepted
        # chunk actually reached the model and succeeded (guide section
        # 9.1: "never describe partial analysis as a full incident review").
        job.state = "partial"
    else:
        job.state = "completed"

    store.save(job)
    _LOG.info("job_finished", job_id=job_id, state=job.state)
