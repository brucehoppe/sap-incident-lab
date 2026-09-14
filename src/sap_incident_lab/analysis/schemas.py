from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PROMPT_VERSION = "extract-v1"


class SourceRef(BaseModel):
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class Observation(BaseModel):
    id: str = Field(max_length=32)
    text: str = Field(max_length=500)
    refs: list[SourceRef] = Field(default_factory=list, max_length=5)


class Hypothesis(BaseModel):
    text: str = Field(max_length=500)
    supporting_observation_ids: list[str] = Field(default_factory=list, max_length=10)
    contradicting_observation_ids: list[str] = Field(default_factory=list, max_length=10)
    checks: list[str] = Field(default_factory=list, max_length=5)


class TimelineEntry(BaseModel):
    raw_timestamp: str | None = Field(default=None, max_length=64)
    event: str = Field(max_length=300)
    ref: SourceRef | None = None


class ModelExtraction(BaseModel):
    """Everything the model is allowed to produce for one chunk (guide section
    9.3). Every list and string is bounded, so a runaway generation cannot
    make a chunk result unboundedly large or hold unlimited hallucinated
    content — this is the *only* part of a chunk result the model supplies;
    identity, timing, and coverage fields are added by code afterward and the
    model never sees or sets them (see ChunkOutcome below).
    """

    observations: list[Observation] = Field(default_factory=list, max_length=30)
    hypotheses: list[Hypothesis] = Field(default_factory=list, max_length=10)
    timeline: list[TimelineEntry] = Field(default_factory=list, max_length=30)
    search_terms: list[str] = Field(default_factory=list, max_length=10)
    missing_information: list[str] = Field(default_factory=list, max_length=10)


ChunkStatus = Literal[
    "completed",
    "oversize_skipped",
    "invalid_output",
    "truncated_output",
    "unprocessed",
]


class ChunkOutcome(BaseModel):
    """The record persisted for one chunk. `extraction` is None for every
    status except 'completed'. Fields below this line are app-owned: the
    model never supplies job_id, chunk_id, file_id, sha256, model, prompt
    version, or timing — see docs/implementation-guide.md section 9.3."""

    job_id: str
    chunk_id: str
    file_id: str
    sha256: str
    start_line: int
    end_line: int
    status: ChunkStatus
    extraction: ModelExtraction | None = None
    invalid_refs_dropped: int = 0
    model: str = ""
    prompt_version: str = PROMPT_VERSION
    elapsed_seconds: float = 0.0
    repair_attempted: bool = False
