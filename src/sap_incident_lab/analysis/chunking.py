from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Chunk:
    """One deterministic, bounded slice of a file. `chunk_id` is derived
    purely from file_id and the line range, so the same file plus the same
    chunking settings always produces the same chunk IDs (DESIGN.md section
    9: "same file + same settings -> same chunk IDs")."""

    chunk_id: str
    file_id: str
    start_line: int  # 1-based, inclusive
    end_line: int  # 1-based, inclusive
    lines: list[str]
    oversize: bool  # a single line exceeded max_chars; not sent to the model


def chunk_lines(
    file_id: str,
    lines: list[str],
    *,
    start_line: int,
    end_line: int,
    max_lines: int,
    max_chars: int,
    overlap_lines: int,
) -> list[Chunk]:
    """Chunk lines[start_line-1 : end_line] (1-based, inclusive) into blocks
    bounded by both max_lines and max_chars, with overlap_lines of overlap
    between consecutive chunks. A single line longer than max_chars becomes
    its own one-line 'oversize' chunk rather than being silently truncated
    (guide section 9.1) — the caller decides what to do with it (skip and
    report, per DESIGN.md section 9).
    """
    chunks: list[Chunk] = []
    pos = start_line  # 1-based cursor
    while pos <= end_line:
        idx = pos  # 1-based
        count = 0
        chars = 0
        oversize = False
        while idx <= end_line and count < max_lines:
            line = lines[idx - 1]
            if len(line) > max_chars:
                if count == 0:
                    # This one line alone exceeds the budget: it becomes its
                    # own chunk so it is reported, never merged silently.
                    oversize = True
                    idx += 1
                    count = 1
                break
            if count > 0 and chars + len(line) > max_chars:
                break
            chars += len(line)
            idx += 1
            count += 1
        chunk_end = idx - 1  # 1-based inclusive
        chunk_lines_slice = lines[pos - 1 : chunk_end]
        chunks.append(
            Chunk(
                chunk_id=f"{file_id}:{pos}-{chunk_end}",
                file_id=file_id,
                start_line=pos,
                end_line=chunk_end,
                lines=chunk_lines_slice,
                oversize=oversize,
            )
        )
        if chunk_end >= end_line:
            break
        next_pos = chunk_end + 1 - overlap_lines
        pos = next_pos if next_pos > pos else chunk_end + 1
    return chunks
