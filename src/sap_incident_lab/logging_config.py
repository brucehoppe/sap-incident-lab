from __future__ import annotations

import logging
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any, cast

import structlog

# Field names that must never reach a log line. Evidence text and full model
# output are excluded by never being passed to structlog in the first place —
# this list only catches config/secret-shaped values that end up in kwargs.
_SENSITIVE_KEYS = {
    "access_token",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
}


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: "[redacted]" if key.lower() in _SENSITIVE_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _redact_event_dict(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], _redact(dict(event_dict)))


def configure_logging(level: str = "INFO") -> None:
    """Route all logging to stderr. stdout is reserved for the MCP JSON-RPC stream."""
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stderr)
    structlog.configure(
        processors=[
            _redact_event_dict,
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
