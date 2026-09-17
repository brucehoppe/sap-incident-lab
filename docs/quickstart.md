# SAP Incident Lab: first investigation

The everyday workflow is: add selected text exports, ask a question in Claude, review the evidence, and save a report. No manifest editing or file IDs are required to start.

## Install and set up once

On Windows, after cloning this repository, run:

```powershell
.\scripts\setup-windows.ps1
```

The installer installs dependencies, pulls the selected Ollama model, runs the full test suite once, creates data folders, registers Claude Desktop, and runs diagnostics. It stops on Git, dependency, test, or diagnostic failures. Git access to this private repository must already work. Python is provisioned by uv according to the project's Python requirement.

On macOS, from this checkout with uv and Ollama installed:

```sh
uv sync --locked --extra dev
uv run sap-incident-lab setup --pull-model
uv run sap-incident-lab doctor
```

The default model is `qwen3.5:9b`, a practical choice for a 24 GB Mac. On a
32 GB Windows machine, select the larger model explicitly:

```powershell
.\scripts\setup-windows.ps1 -Model qwen3.8
```

Ollama must be running before downloading or testing the model. To choose your folder and model interactively:

```sh
uv run sap-incident-lab setup --interactive --pull-model
```

Defaults are `~/SAPIncidentLabData/incidents`, `~/SAPIncidentLabData/outputs`, and `qwen3.5:9b`. Use `setup --data-dir PATH --model NAME` to select any installed Ollama tag. `setup --no-desktop` configures command-line use without Desktop registration.

You can configure a fallback model for missing primary tags:

```sh
uv run sap-incident-lab setup --model qwen3.5:9b --fallback-model qwen3:8b --pull-model
```

Fallback is used only when Ollama reports that the primary model is missing;
the actual model used is recorded in each chunk result. Compare models with:

```sh
uv run sap-incident-lab benchmark --models qwen3.5:9b qwen3:8b --json
```

Setup stores configuration at `~/.config/sap-incident-lab/config.json`. Environment variables and local dotenv settings override saved defaults. Use the global `--config PATH` option before any command to keep an independent installation, or set `INCIDENT_LAB_CONFIG`.

Existing configuration is backed up before replacement. Other Desktop servers and existing evidence are preserved. Rerunning setup without folder/model arguments retains the saved choices. The Desktop entry uses this installation's absolute Python executable; rerun setup if you move or recreate the installation.

Fully quit and reopen Claude Desktop after registration. Setup writes configuration; `doctor` verifies folders and the local model. Neither proves that Desktop has reloaded its configuration—ask Claude to check Incident Lab health.

## Try the bundled demo

```sh
uv run sap-incident-lab demo
```

Then ask Claude:

> Investigate INC-DEMO-001 and explain why the import failed. Show the evidence and any gaps in coverage.

The bundled exports are synthetic. The importer copies only the two evidence files and creates the manifest; it does not include an answer key. Reimporting an existing incident is refused so existing files cannot be overwritten.

Claude can call `incident_lab_investigate` with the incident ID and question. It selects all registered files and starts a bounded batch. Empty files are disclosed. Use a more focused question or the existing range tools for targeted work.

## Add your exports

Choose the text files explicitly:

```powershell
uv run sap-incident-lab import INC-123 'C:\exports\import.log' 'C:\exports\trace.txt' --summary 'Import stopped after restart'
```

On macOS:

```sh
uv run sap-incident-lab import INC-123 "/path/to/import.log" "/path/to/trace.txt"
```

The command validates copied bytes and creates `incident.json` automatically. Originals remain unchanged. Directories, symlinks, duplicate filenames, reserved manifest/answer-key filenames, invalid text, and oversized files are rejected. A failed import does not leave a completed incident behind.

Specify `--encoding cp1252` if that is the export's actual encoding. Use `--sid ABC` and `--timezone America/Toronto` only when known. Omitted system facts and time zones remain unknown rather than being guessed.

Now ask:

> Investigate INC-123. What explains the failure, and what should I check next?

Import is a local CLI operation. The MCP server has no tool for browsing or importing arbitrary local files.

## Progress and resume

Ask Claude:

> Show the investigation's progress. Continue the remaining work without repeating successful chunks.

`incident_lab_get_analysis` returns a plain-language summary, coverage percentage, completed/failed/pending/skipped counts, and the next action. Failed chunks are part of remaining work; they must not be counted twice. Coverage is measured in chunks, not confidence or proof of root cause.

`incident_lab_resume_analysis` continues the same job with one bounded batch per call, retaining successful results. Each batch uses the configured chunk limit. It retries failed output and processes remaining chunks. The server permits only one active job.

Resume checks the recorded source hashes, model name and prompt version before making changes. If evidence changed, start a new investigation. Older jobs created before resumable plans were introduced remain readable but cannot resume. Oversize skipped lines need shorter exports; resume does not silently truncate them.

Cancelled and interrupted jobs can resume. A normal server shutdown marks interrupted work and preserves completed chunks; after a crash, startup recovers unfinished jobs.

## Save a report

Ask Claude:

> Prepare a report using the Incident Lab report template. Verify each finding against exact evidence lines, separate hypotheses from facts, disclose missing coverage, and save the report.

The template contains summary, scope and coverage, evidence inventory with hashes, findings and evidence, hypotheses, missing information, next checks, and limitations. It leaves conclusions blank for the analyst and flags changed sources. Coverage from overlapping jobs must not be added together.

Saved reports are versioned Markdown under the output folder. Saving does not mechanically verify claims or citations.

## If something does not work

Run:

```sh
uv run sap-incident-lab doctor
```

It checks configuration, actual folder access, the Ollama model inventory, and a small synthetic structured extraction. Each failed check provides a next step. A failed diagnostic exits with code 1.

- Ollama unavailable: start Ollama, then rerun doctor.
- Model missing: run the displayed `ollama pull` command.
- Folder failure: fix permissions or select another data folder with setup.
- Invalid extraction: check the model, then retry doctor.
- Source changed: reinvestigate the current exports.
- Incident already exists: use a new incident ID; imports never overwrite existing evidence.

`doctor --no-extraction` skips inference and is only a configuration/connectivity check. `doctor --json` provides machine-readable results. The older `probe` command is an alias for doctor.

## Acceptance checklist for a fresh Windows machine

1. Clone the private repository using working Git credentials and run the Windows setup script.
2. Confirm tests and doctor pass. Restart Desktop and confirm Incident Lab and existing MCP servers are available.
3. Run the demo and request an investigation using only its ID and a question.
4. Review progress and exact evidence, request the report template, and save a report.
5. Rerun setup and confirm evidence, reports, saved settings and other MCP servers remain intact.
6. Import selected text exports without editing JSON; check unknown metadata stays unknown.

Automated tests cover the synthetic workflow, including bounded resume, through the real in-process MCP client with mocked Ollama. PowerShell control-flow checks stub external programs. Those checks do not substitute for installing Ollama and using Claude Desktop on Windows.

## Maintainer verification

```sh
uv run pytest
uv run ruff check src tests scripts/consumer-check.py
uv run mypy src
pwsh -NoProfile -File tests/windows/setup-script.Tests.ps1
uv build
uv run python scripts/consumer-check.py dist/sap_incident_lab-0.1.0-py3-none-any.whl
```

The consumer check creates a fresh environment, installs the wheel with the locked
runtime dependencies, runs setup/demo/repeat setup in temporary folders, and launches
the generated Desktop command over real stdio MCP. It does not modify your Desktop
configuration. Add `--offline` when all dependencies are cached.

The GitHub workflow runs these checks on macOS and Windows after push/PR, and can
also be started manually. Hosted verification remains pending until that workflow
has run; graphical Desktop acceptance remains a separate target-machine check.
