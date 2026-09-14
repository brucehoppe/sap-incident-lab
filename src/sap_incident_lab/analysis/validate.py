from __future__ import annotations

from .schemas import ModelExtraction, Observation, TimelineEntry


def _ref_in_range(ref_start: int, ref_end: int, chunk_start: int, chunk_end: int) -> bool:
    return chunk_start <= ref_start <= ref_end <= chunk_end


def clip_invalid_refs(
    extraction: ModelExtraction, start_line: int, end_line: int
) -> tuple[ModelExtraction, int]:
    """Drop every reference that falls outside the chunk the model actually
    saw (guide section 9.4: "reject invalid references"). An observation
    that had refs but has none left after clipping is dropped entirely — an
    unsupported claim is worse than a missing one. An observation that
    never had any refs is left alone (the model is allowed to state it found
    nothing to cite). Returns the filtered extraction and how many
    individual refs were dropped, so the caller can report it rather than
    silently swallow it.
    """
    dropped = 0
    kept_observations: list[Observation] = []
    for obs in extraction.observations:
        if not obs.refs:
            kept_observations.append(obs)
            continue
        good_refs = [
            r for r in obs.refs if _ref_in_range(r.start_line, r.end_line, start_line, end_line)
        ]
        dropped += len(obs.refs) - len(good_refs)
        if good_refs:
            kept_observations.append(obs.model_copy(update={"refs": good_refs}))
        # else: every ref was bad -> drop the observation, it has no support left

    kept_timeline: list[TimelineEntry] = []
    for entry in extraction.timeline:
        if entry.ref is None:
            kept_timeline.append(entry)
            continue
        if _ref_in_range(entry.ref.start_line, entry.ref.end_line, start_line, end_line):
            kept_timeline.append(entry)
        else:
            dropped += 1

    filtered = extraction.model_copy(
        update={"observations": kept_observations, "timeline": kept_timeline}
    )
    return filtered, dropped
