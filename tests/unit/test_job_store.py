from __future__ import annotations

from pathlib import Path

from sap_incident_lab.analysis.schemas import ChunkOutcome
from sap_incident_lab.jobs.store import JobRecord, JobStore, new_job_id, now_iso


def _job(job_id: str, state: str = "queued") -> JobRecord:
    return JobRecord(
        job_id=job_id,
        incident_id="INC-SYN-001",
        file_ids=["f01"],
        question="q",
        state=state,  # type: ignore[arg-type]
        created_at=now_iso(),
        model="qwen3:8b",
    )


def test_create_and_load_round_trips(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    job = _job(new_job_id("INC-SYN-001"))
    store.create(job)

    loaded = store.load(job.job_id)
    assert loaded is not None
    assert loaded.job_id == job.job_id
    assert loaded.state == "queued"


def test_load_unknown_job_returns_none(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    assert store.load("does-not-exist") is None


def test_save_chunk_result_and_list_are_sorted_by_position(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    job = _job(new_job_id("INC-SYN-001"))
    store.create(job)

    for start, end in [(10, 12), (1, 5), (6, 9)]:
        store.save_chunk_result(
            job.job_id,
            ChunkOutcome(
                job_id=job.job_id,
                chunk_id=f"f01:{start}-{end}",
                file_id="f01",
                sha256="abc",
                start_line=start,
                end_line=end,
                status="completed",
            ),
        )

    results = store.list_chunk_results(job.job_id)
    assert [r.start_line for r in results] == [1, 6, 10]


def test_recover_interrupted_jobs_marks_only_live_states(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    running = _job(new_job_id("INC-SYN-001"), state="running")
    completed = _job(new_job_id("INC-SYN-001"), state="completed")
    cancelling = _job(new_job_id("INC-SYN-001"), state="cancelling")
    store.create(running)
    store.create(completed)
    store.create(cancelling)

    recovered = store.recover_interrupted_jobs()

    assert set(recovered) == {running.job_id, cancelling.job_id}
    assert store.load(running.job_id).state == "interrupted"  # type: ignore[union-attr]
    assert store.load(completed.job_id).state == "completed"  # type: ignore[union-attr]
    assert store.load(cancelling.job_id).state == "interrupted"  # type: ignore[union-attr]


def test_recover_interrupted_jobs_sets_ended_at(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    job = _job(new_job_id("INC-SYN-001"), state="running")
    store.create(job)

    store.recover_interrupted_jobs()

    reloaded = store.load(job.job_id)
    assert reloaded is not None
    assert reloaded.ended_at is not None


def test_find_live_job_returns_running_job_id(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    done = _job(new_job_id("INC-SYN-001"), state="completed")
    running = _job(new_job_id("INC-SYN-001"), state="running")
    store.create(done)
    store.create(running)

    assert store.find_live_job() == running.job_id


def test_find_live_job_returns_none_when_nothing_is_live(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    store.create(_job(new_job_id("INC-SYN-001"), state="completed"))
    store.create(_job(new_job_id("INC-SYN-001"), state="failed"))

    assert store.find_live_job() is None


def test_atomic_write_leaves_no_tmp_file_behind(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    job = _job(new_job_id("INC-SYN-001"))
    store.create(job)
    job.state = "completed"
    store.save(job)

    leftovers = list(store.jobs_dir.rglob("*.tmp-*"))
    assert leftovers == []


def test_job_paths_reject_traversal_and_external_symlinks(tmp_path: Path) -> None:
    import pytest

    from sap_incident_lab.errors import ToolError

    store = JobStore(tmp_path / "output")
    for job_id in ("../escape", "/tmp/escape", r"..\escape", "C:escape", ""):
        with pytest.raises(ToolError):
            store.load(job_id)
    outside = tmp_path / "outside"
    outside.mkdir()
    (store.jobs_dir / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ToolError):
        store.load("linked")


def test_job_metadata_symlink_cannot_read_outside_output(tmp_path: Path) -> None:
    import pytest

    from sap_incident_lab.errors import ToolError

    store = JobStore(tmp_path / "output")
    job = _job("test-job")
    store.create(job)
    outside = tmp_path / "outside.json"
    outside.write_text(job.model_dump_json())
    metadata = store.jobs_dir / job.job_id / "job.json"
    metadata.unlink()
    metadata.symlink_to(outside)
    with pytest.raises(ToolError):
        store.load(job.job_id)


def test_recovery_counts_unfinished_coverage(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    job = _job("test-job")
    job.accepted_chunk_ids = ["f01:1-2", "f01:3-4", "f01:5-6"]
    job.processed_chunk_ids = ["f01:1-2"]
    job.skipped_chunk_ids = ["f01:3-4"]
    job.unprocessed_chunk_ids = ["f01:7-8"]
    store.create(job)
    store.recover_interrupted_jobs()
    recovered = store.load(job.job_id)
    assert recovered is not None
    assert recovered.unprocessed_chunk_ids == ["f01:5-6", "f01:7-8"]
