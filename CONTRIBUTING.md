# Contributing

## Development

Use Python 3.14 and uv:

```sh
uv sync --locked --extra dev
uv run pytest
uv run ruff check src tests scripts/consumer-check.py
uv run mypy src
uv build
```

Only synthetic evidence belongs in the repository. Do not add real SAP logs,
hostnames, SIDs, credentials, answer keys, or institutional configuration.

## Changes

Preserve the read-only evidence boundary, bounded outputs, source-hash
provenance, and explicit partial-coverage semantics. Add or update tests for
security-sensitive behavior and update `CHANGELOG.md` for user-visible work.

Before a release, run the clean-wheel consumer check and verify the target
platform separately. Passing mocked Ollama tests does not prove live model,
Windows, or Claude Desktop compatibility.
