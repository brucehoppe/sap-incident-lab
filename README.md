# SAP Incident Lab

A local, read-only MCP server that lets Claude Desktop investigate exported
SAP incidents using a local Qwen model through Ollama, with every claim
traceable back to exact source lines. See [`DESIGN.md`](DESIGN.md) for the
architecture and [`docs/implementation-guide.md`](docs/implementation-guide.md)
for the original planning document it corrects.

## Status

Milestones 0–4 are done: all seven tool contracts work end-to-end against a
synthetic incident, including one live run through a real `qwen3:8b` model.
See [`DESIGN.md`](DESIGN.md) section 12 for the milestone table.

- `incident_lab_health` — server/Ollama/config status
- `incident_lab_list_incidents`, `incident_lab_list_files`, `incident_lab_get_evidence`
  — the evidence layer: hashed, path-contained, exact numbered source lines
- `incident_lab_start_analysis`, `incident_lab_get_analysis`, `incident_lab_cancel_analysis`
  — bounded, chunked Qwen extraction as an async job, with restart recovery
- `incident_lab_save_report` — versioned, Claude-authored Markdown reports

99 tests pass (`uv run pytest`); ruff and `mypy --strict` are clean.

With no resolved incident available, milestones 5–6 became a 4-case synthetic
portfolio instead (`tests/fixtures/INC-SYN-00{1,2,3,4}`) covering distinct
failure shapes — a stale enqueue lock, an infinite-loop batch job, a
memory-exhaustion short dump, an expired RFC certificate. All four ran live
against `qwen3:8b`. See DESIGN.md section 13 for what that run showed,
including a real limitation it found: `hypotheses` came back empty in every
one of 8 chunks, even where the observations already contained the answer.

Milestone 7 (publication) still needs your sign-off on releasing this repo
publicly. Milestone 5 in its original sense — a real resolved incident —
is now just "whenever the next real incident happens" rather than a
scheduled step; see DESIGN.md sections 3 and 14.

## Setup

```bash
uv sync --extra dev
cp config.example.env .env.local   # then edit paths
uv run sap-incident-lab probe      # smoke-test Ollama directly
uv run pytest -q
```

## Run as an MCP server

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`,
alongside any existing `mcpServers` entries — see DESIGN.md section 10 for
the full example.

## Data

Real incident evidence never lives in this repository. It lives under a
separate data root (`INCIDENT_LAB_ROOT`) that only this server reads, and an
`evaluation-private/` directory that is never configured into the server.
Synthetic fixtures under `tests/fixtures/` are the only incident data
committed here.
