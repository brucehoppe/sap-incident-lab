from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from sap_incident_lab.analysis.schemas import ModelExtraction, Observation, SourceRef
from sap_incident_lab.analysis.worker import RangeRequest, plan_chunks, run_job
from sap_incident_lab.config import Settings
from sap_incident_lab.jobs.store import JobRecord, JobStore, new_job_id, now_iso


def _patch_ollama(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    real_client = httpx.AsyncClient

    def patched(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr("sap_incident_lab.analysis.ollama_client.httpx.AsyncClient", patched)


def _valid_response(observation_start_line: int) -> httpx.Response:
    extraction = ModelExtraction(
        observations=[
            Observation(
                id="o1",
                text="stale enqueue lock",
                refs=[SourceRef(start_line=observation_start_line, end_line=observation_start_line)],
            )
        ]
    )
    return httpx.Response(
        200, json={"done_reason": "stop", "message": {"content": extraction.model_dump_json()}}
    )


def _new_job(store: JobStore, incident_id: str, file_ids: list[str], accepted_ids: list[str]) -> JobRecord:
    job = JobRecord(
        job_id=new_job_id(incident_id),
        incident_id=incident_id,
        file_ids=file_ids,
        question="why did it fail?",
        state="queued",
        created_at=now_iso(),
        model="qwen3:8b",
        accepted_chunk_ids=accepted_ids,
    )
    store.create(job)
    return job


@pytest.mark.asyncio
async def test_full_job_completes_against_the_synthetic_fixture(
    monkeypatch: pytest.MonkeyPatch, synthetic_incident: Settings
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        start_line = int(body["messages"][1]["content"].split("Line range: ")[1].split("-")[0])
        return _valid_response(start_line)

    _patch_ollama(monkeypatch, handler)
    assert synthetic_incident.output is not None
    store = JobStore(synthetic_incident.output)

    chunks, file_hashes = plan_chunks(synthetic_incident, "INC-SYN-001", ["f02"], None)
    job = _new_job(store, "INC-SYN-001", ["f02"], [c.chunk_id for c in chunks])

    await run_job(
        synthetic_incident, store, job.job_id, chunks, file_hashes, job.question, asyncio.Event()
    )

    finished = store.load(job.job_id)
    assert finished is not None
    assert finished.state == "completed"
    results = store.list_chunk_results(job.job_id)
    assert all(r.status == "completed" for r in results)
    assert all(r.sha256 == file_hashes["f02"] for r in results)


@pytest.mark.asyncio
async def test_oversize_chunk_is_skipped_without_calling_ollama(
    monkeypatch: pytest.MonkeyPatch, synthetic_incident: Settings
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _valid_response(1)

    _patch_ollama(monkeypatch, handler)
    synthetic_incident.max_chunk_chars = 5  # forces every real line to be "oversize"
    assert synthetic_incident.output is not None
    store = JobStore(synthetic_incident.output)

    chunks, file_hashes = plan_chunks(synthetic_incident, "INC-SYN-001", ["f01"], None)
    assert all(c.oversize for c in chunks)
    job = _new_job(store, "INC-SYN-001", ["f01"], [c.chunk_id for c in chunks])

    await run_job(
        synthetic_incident, store, job.job_id, chunks, file_hashes, job.question, asyncio.Event()
    )

    assert calls == 0
    finished = store.load(job.job_id)
    assert finished is not None
    assert finished.state == "partial"  # nothing processed via the model, but nothing crashed either
    assert len(finished.skipped_chunk_ids) == len(chunks)


@pytest.mark.asyncio
async def test_cancel_event_stops_before_the_next_chunk(
    monkeypatch: pytest.MonkeyPatch, synthetic_incident: Settings
) -> None:
    cancel_event = asyncio.Event()
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        cancel_event.set()  # cancel after the first chunk is in flight
        return _valid_response(1)

    _patch_ollama(monkeypatch, handler)
    synthetic_incident.max_chunk_lines = 1  # one line per chunk -> several chunks for this file
    assert synthetic_incident.output is not None
    store = JobStore(synthetic_incident.output)

    chunks, file_hashes = plan_chunks(synthetic_incident, "INC-SYN-001", ["f02"], None)
    assert len(chunks) > 1
    job = _new_job(store, "INC-SYN-001", ["f02"], [c.chunk_id for c in chunks])

    await run_job(synthetic_incident, store, job.job_id, chunks, file_hashes, job.question, cancel_event)

    finished = store.load(job.job_id)
    assert finished is not None
    assert finished.state == "cancelled"
    assert call_count == 1  # never called again once the event was set
    assert len(finished.unprocessed_chunk_ids) == len(chunks) - 1


@pytest.mark.asyncio
async def test_all_invalid_output_marks_job_failed(
    monkeypatch: pytest.MonkeyPatch, synthetic_incident: Settings
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"done_reason": "stop", "message": {"content": "not json"}})

    _patch_ollama(monkeypatch, handler)
    assert synthetic_incident.output is not None
    store = JobStore(synthetic_incident.output)

    chunks, file_hashes = plan_chunks(synthetic_incident, "INC-SYN-001", ["f01"], None)
    job = _new_job(store, "INC-SYN-001", ["f01"], [c.chunk_id for c in chunks])

    await run_job(
        synthetic_incident, store, job.job_id, chunks, file_hashes, job.question, asyncio.Event()
    )

    finished = store.load(job.job_id)
    assert finished is not None
    assert finished.state == "failed"
    results = store.list_chunk_results(job.job_id)
    assert all(r.status == "invalid_output" for r in results)
    # a repair attempt was made and still failed, and that is recorded
    assert all(r.repair_attempted for r in results)


@pytest.mark.asyncio
async def test_range_request_narrows_scope(synthetic_incident: Settings) -> None:
    chunks, file_hashes = plan_chunks(
        synthetic_incident,
        "INC-SYN-001",
        ["f02"],
        [RangeRequest("f02", 2, 3)],
    )
    assert len(chunks) == 1
    assert chunks[0].start_line == 2
    assert chunks[0].end_line == 3
    assert "f02" in file_hashes
