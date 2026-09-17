# Privacy and data handling

SAP Incident Lab does not provide a central hosted inference service. It reads
selected evidence from the configured local root and sends bounded excerpts to
the configured Ollama endpoint, which must be loopback-only.

However, the MCP result is delivered to the connected AI client. If that
client is cloud-backed or institutionally managed, the evidence may leave the
machine under that client's policies. Operators must confirm classification,
retention, access, and approved use before importing real incident data.

The application preserves original bytes and hashes for traceability. It does
not currently provide automatic redaction or guarantee that sensitive values
are absent from model output. Treat exported SAP logs as sensitive by default.

For a non-destructive preview of common email, IPv4, bearer-token, and
secret-assignment patterns, use `sap-incident-lab redact-preview FILE`. This
does not alter the source file or its evidence hash; it is a convenience aid,
not a complete privacy review.
