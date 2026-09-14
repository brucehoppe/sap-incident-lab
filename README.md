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

91 tests pass (`uv run pytest`); ruff and `mypy --strict` are clean.

Milestones 5–7 (a real incident, evaluation, publication) need a resolved
incident, the Windows work laptop and institutional Claude Desktop, and your
sign-off on data classification — see DESIGN.md sections 3 and 13.

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
