# Changelog

## Unreleased

- Added host-appropriate primary and fallback Ollama model profiles.
- Added bounded model benchmarking with structured-output validation.
- Added model selection and fallback reporting to setup and diagnostics.
- Evidence retrieval now reads only the requested file instead of the whole incident.
- Saved reports are size-bounded and their job IDs validated before being written.
- Untrusted-excerpt delimiters carry a per-request nonce so evidence cannot forge them.
- The Ollama URL must be a credential-free http(s) loopback URL; manifests are bounded
  to 200 files.
- Setup creates the evidence and output folders owner-only (0700) on macOS/Linux.
- CI actions are pinned to commit SHAs and Dependabot tracks uv and action updates.

## 0.1.0

- Initial local MCP server, bounded evidence registry, resumable analysis jobs,
  report templates, synthetic demo, and macOS/Windows verification workflow.
