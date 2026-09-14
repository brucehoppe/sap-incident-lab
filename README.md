# SAP Incident Lab

A local, read-only MCP server that lets Claude Desktop investigate exported
SAP incidents using a local Qwen model through Ollama, with every claim
traceable back to exact source lines. See [`DESIGN.md`](DESIGN.md) for the
architecture and [`docs/implementation-guide.md`](docs/implementation-guide.md)
for the original planning document it corrects.

## Start here

See the [first-investigation walkthrough](docs/quickstart.md) for setup, import,
progress, resume, and reports. After installing uv and Ollama:

```sh
uv sync --locked --extra dev
uv run sap-incident-lab setup --pull-model
uv run sap-incident-lab doctor
uv run sap-incident-lab demo
```

Restart Claude Desktop, then ask:

> Investigate INC-DEMO-001 and explain why the import failed.

To investigate your exports, run `sap-incident-lab import INC-123 FILE [FILE ...]`.
The importer creates the manifest; unknown metadata stays unknown. Run `setup --interactive` to choose your folder/model, or `setup --no-desktop` for CLI-only
configuration. Setup backs up existing configuration and preserves other servers.

## Tools

- `incident_lab_health` — server/Ollama/configuration status.
- `incident_lab_investigate` — inventory and start analysis using an incident ID and question.
- `incident_lab_get_analysis`, `incident_lab_resume_analysis`,
  `incident_lab_cancel_analysis` — progress, bounded continuation, and cancellation.
- `incident_lab_report_template`, `incident_lab_save_report` — consistent report
  scaffolds and versioned Markdown.
- `incident_lab_list_incidents`, `incident_lab_list_files`,
  `incident_lab_get_evidence`, `incident_lab_start_analysis` — detailed inventory,
  exact source lines, and targeted analysis.

Resume preserves successful chunks and checks source hashes before continuing.
Coverage is explicit; partial extraction is never a complete incident review.
Reports remain analyst-authored and require citation review.

## Validation

Run `uv run pytest`, `uv run ruff check src tests`, and `uv run mypy src`.
The synthetic walkthrough covers setup, demo import, investigation, progress,
resume, evidence retrieval and report saving through the MCP client. Model
responses in automated tests are mocked. Native Windows, real Ollama and
Claude Desktop acceptance must be verified on the target machine.

The original four-case synthetic portfolio and its live Qwen observations are
documented in DESIGN.md. Real resolved-incident evaluation remains pending;
publication remains a separate decision.

## Setting up on Windows

`scripts/setup-windows.ps1` automates the move to a Windows machine: installs
uv if missing, installs/pulls Ollama and the model, clones or updates the
repo, runs `uv sync` and the test suite (including the `windows_only` tests
that can't be proven on the Mac this was built on), creates the data
directories, and merges the Claude Desktop entry (backing up the existing
config first, leaving other servers untouched).

The repo is private, so fetching the script needs an authenticated `git clone`
first — it can't be piped from a raw GitHub URL without a token. From a
fresh Windows machine with git and an SSH key registered on your GitHub
account:

```powershell
git clone git@github.com:bruce-hoppe_uoft/sap-incident-lab.git
cd sap-incident-lab
.\scripts\setup-windows.ps1
```

The script itself also clones/updates the repo (to `-InstallDir`, default
`%USERPROFILE%\sap-incident-lab`), so re-running it from anywhere keeps it
up to date — see the script's own `.SYNOPSIS`/parameter docs for options.

## Run as an MCP server

The setup command registers the server with Claude Desktop automatically.
For other MCP clients, run `sap-incident-lab serve` over stdio and provide
`INCIDENT_LAB_CONFIG` or the documented environment variables.

## Data

Real incident evidence never lives in this repository. It lives under a
separate data root (`INCIDENT_LAB_ROOT`) that only this server reads, and an
`evaluation-private/` directory that is never configured into the server.
Only synthetic fixtures under `tests/fixtures/` and the bundled
`src/sap_incident_lab/demo/` evidence are committed here.
