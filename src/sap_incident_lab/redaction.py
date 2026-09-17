from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RedactionResult:
    text: str
    counts: dict[str, int]


_PATTERNS = (
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I), "[REDACTED_EMAIL]"),
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[REDACTED_IPV4]"),
    ("bearer", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED_TOKEN]"),
    ("secret_assignment", re.compile(r"(?i)\b(password|passwd|secret|token)\s*[=:]\s*[^\s,;]+"), r"\1=[REDACTED_SECRET]"),
)


def redact_text(text: str) -> RedactionResult:
    counts: dict[str, int] = {}
    redacted = text
    for name, pattern, replacement in _PATTERNS:
        redacted, count = pattern.subn(replacement, redacted)
        if count:
            counts[name] = count
    return RedactionResult(redacted, counts)
