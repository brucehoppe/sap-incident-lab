# Security policy

## Scope

SAP Incident Lab is a local, read-only evidence-analysis assistant. Evidence
is read from a configured root, sent to the configured loopback Ollama service,
and returned through the MCP client. Tool output may enter the host AI
conversation; local Ollama does not make that conversation local.

Do not use real incident exports until their data classification, retention,
and approved Claude environment have been confirmed. The repository contains
synthetic fixtures only. Never commit credentials, tokens, private keys, PSEs,
production certificates, or real incident evidence.

## Reporting a vulnerability

Do not open a public issue containing sensitive details. Contact the repository
maintainer privately with a description, affected version, reproduction steps,
and impact. Allow time for a fix and coordinated disclosure.

## Security boundaries

- Ollama endpoints must be loopback-only.
- Evidence paths are manifest-controlled and containment-checked.
- Evidence is bounded by file, chunk, line, character, and result limits.
- Source hashes are checked before citation retrieval and resume.
- Logs exclude evidence text and redact common secret-shaped fields.
- Reports are labelled analyst-authored and mechanically unverified.
