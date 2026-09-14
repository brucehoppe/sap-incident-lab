from __future__ import annotations

import asyncio

import httpx
import pytest

from sap_incident_lab.analysis.worker import run_job
from sap_incident_lab.analysis.workflow import create_analysis, progress, resume_analysis
from sap_incident_lab.config import Settings
from sap_incident_lab.errors import ToolError
from sap_incident_lab.jobs.store import JobStore

REAL_CLIENT = httpx.AsyncClient


def patch_http(monkeypatch, handler) -> None:
    real = REAL_CLIENT

    def patched(*args, **kwargs):
        return real(*args, **{**kwargs, "transport": httpx.MockTransport(handler)})

    monkeypatch.setattr("httpx.AsyncClient", patched)


async def finish(settings, store, job, chunks):
    await run_job(
        settings, store, job.job_id, chunks, job.file_hashes, job.question, asyncio.Event()
    )
    return store.load(job.job_id)


async def test_resume_continues_budget_without_repeating_success(
    synthetic_incident: Settings, monkeypatch
) -> None:
    settings = synthetic_incident
    settings.max_chunks_per_job = 1
    settings.max_chunk_lines = 2
    settings.chunk_overlap_lines = 0
    calls = []

    def handler(request):
        calls.append(request.content)
        return httpx.Response(200, json={"message": {"content": '{"observations": []}'}})

    patch_http(monkeypatch, handler)
    store = JobStore(settings.output)
    job, chunks = create_analysis(settings, store, "INC-SYN-001", ["f01"], "What happened?")
    total = len(job.plan)
    assert total > 1
    job = await finish(settings, store, job, chunks)
    first_result = store.list_chunk_results(job.job_id)[0].model_dump()
    assert job.state == "partial"
    assert progress(store, job)["can_resume"]
    for _ in range(total - 1):
        job, chunks = resume_analysis(settings, store, job.job_id)
        assert len(chunks) == 1
        job = await finish(settings, store, job, chunks)
    assert job.state == "completed"
    assert progress(store, job)["coverage_percent"] == 100
    assert len(calls) == total
    assert first_result == store.list_chunk_results(job.job_id)[0].model_dump()
    assert not job.unprocessed_chunk_ids


async def test_resume_retries_failed_output(synthetic_incident: Settings, monkeypatch) -> None:
    settings = synthetic_incident
    patch_http(
        monkeypatch, lambda request: httpx.Response(200, json={"message": {"content": "bad"}})
    )
    store = JobStore(settings.output)
    job, chunks = create_analysis(settings, store, "INC-SYN-001", ["f01"], "q")
    job = await finish(settings, store, job, chunks)
    assert progress(store, job)["failed_chunks"] > 0
    patch_http(
        monkeypatch, lambda request: httpx.Response(200, json={"message": {"content": "{}"}})
    )
    job, chunks = resume_analysis(settings, store, job.job_id)
    job = await finish(settings, store, job, chunks)
    assert job.state == "completed"
    assert progress(store, job)["failed_chunks"] == 0


async def test_changed_source_blocks_resume_without_mutation(synthetic_incident: Settings) -> None:
    settings = synthetic_incident
    store = JobStore(settings.output)
    job, chunks = create_analysis(settings, store, "INC-SYN-001", ["f01"], "q")
    store.recover_interrupted_jobs()
    before = store.load(job.job_id).model_dump()
    (settings.root / "INC-SYN-001/import-log.txt").write_text("changed")
    with pytest.raises(ToolError) as exc:
        resume_analysis(settings, store, job.job_id)
    assert exc.value.code == "SOURCE_CHANGED"
    assert store.load(job.job_id).model_dump() == before


async def test_background_exception_is_recoverable(
    synthetic_incident: Settings, monkeypatch
) -> None:
    async def broken(*args, **kwargs):
        raise RuntimeError("private detail")

    monkeypatch.setattr("sap_incident_lab.analysis.worker.extract_with_repair", broken)
    settings = synthetic_incident
    store = JobStore(settings.output)
    job, chunks = create_analysis(settings, store, "INC-SYN-001", ["f01"], "q")
    job = await finish(settings, store, job, chunks)
    assert job.state == "failed"
    assert "private detail" not in job.error
    assert progress(store, job)["can_resume"]


def test_resume_rejects_changed_model_without_mutating_job(synthetic_incident: Settings) -> None:
    settings = synthetic_incident
    store = JobStore(settings.output)
    job, _ = create_analysis(settings, store, "INC-SYN-001", ["f01"], "q")
    store.recover_interrupted_jobs()
    before = store.load(job.job_id).model_dump()
    settings.model = "different-model"
    with pytest.raises(ToolError) as exc:
        resume_analysis(settings, store, job.job_id)
    assert exc.value.code == "RESUME_CONFIG_CHANGED"
    assert store.load(job.job_id).model_dump() == before


async def test_oversize_chunks_are_disclosed_and_not_resumed(synthetic_incident: Settings) -> None:
    settings = synthetic_incident
    settings.max_chunk_chars = 1
    store = JobStore(settings.output)
    job, chunks = create_analysis(settings, store, "INC-SYN-001", ["f01"], "q")
    job = await finish(settings, store, job, chunks)
    detail = progress(store, job)
    assert detail["skipped_chunks"] == detail["total_chunks"]
    assert detail["coverage_percent"] == 0
    assert not detail["can_resume"]
    with pytest.raises(ToolError) as exc:
        resume_analysis(settings, store, job.job_id)
    assert exc.value.code == "NOTHING_TO_RESUME"


async def test_task_cancellation_preserves_a_resumable_job(
    synthetic_incident: Settings, monkeypatch
) -> None:
    entered = asyncio.Event()

    async def extraction(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("sap_incident_lab.analysis.worker.extract_with_repair", extraction)
    settings = synthetic_incident
    store = JobStore(settings.output)
    job, chunks = create_analysis(settings, store, "INC-SYN-001", ["f01"], "q")
    task = asyncio.create_task(
        run_job(settings, store, job.job_id, chunks, job.file_hashes, job.question, asyncio.Event())
    )
    await asyncio.wait_for(entered.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    interrupted = store.load(job.job_id)
    assert interrupted.state == "interrupted"
    assert progress(store, interrupted)["can_resume"]
