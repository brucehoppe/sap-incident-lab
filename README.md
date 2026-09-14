# SAP Incident Lab

A local, read-only MCP server that lets Claude Desktop investigate exported
SAP incidents using a local Qwen model through Ollama, with every claim
traceable back to exact source lines. See [`DESIGN.md`](DESIGN.md) for the
architecture and [`docs/implementation-guide.md`](docs/implementation-guide.md)
for the original planning document it corrects.

## Status

Milestone 0–1 (connectivity): the server starts, registers `incident_lab_health`,
and a synchronous `probe` command confirms Ollama round-trips. Evidence tools
(milestone 2) are not yet implemented.

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
