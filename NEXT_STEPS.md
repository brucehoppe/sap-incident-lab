# Next steps

Follow-ups from the September 2026 code and security review (PR #1). Ordered by
value for the effort. Tick items off here as they land; move anything shipped
into `CHANGELOG.md`.

## 1. Browser demo (portfolio requirement)

The repo is public and has no "Try it in your browser" demo.

- [ ] Add a static page (no backend, no network, no API keys) that replays the
      `INC-DEMO-001` investigation from bundled sample data: inventory → analysis
      progress → evidence lines with hashes → report template.
- [ ] Generate the bundled JSON from the real tool outputs so the demo cannot
      drift from the server's actual response shapes.
- [ ] Use relative asset paths so it works on GitHub Pages.
- [ ] Add a Pages workflow that publishes on push to `main` (SHA-pinned actions,
      `permissions` limited to what Pages needs).
- [ ] Put the demo link at the top of `README.md`, above the install steps.
- [ ] Load it in a real browser and confirm there are no console errors.

## 2. Redact evidence before it leaves the machine

`redact-preview` is CLI-only. Evidence returned by `incident_lab_get_evidence`,
`incident_lab_search_evidence`, and the chunks sent to Ollama are unredacted, and
tool output enters the host AI conversation (see `SECURITY.md`).

- [ ] Add an opt-in `INCIDENT_LAB_REDACT` setting applied to evidence and search
      results, reporting redaction counts alongside the lines.
- [ ] Keep hashes computed over the original bytes, and state in the result that
      the returned text is redacted so a citation is not mistaken for the raw line.
- [ ] Extend `redaction.py` patterns: IPv6, SAP user IDs, hostnames/FQDNs, and
      long hex/base64 tokens. Add tests for false positives on timestamps and
      version strings (the IPv4 pattern currently matches `7.53.1.20`-style
      kernel versions).
- [ ] Document the limits in `docs/privacy.md`: pattern redaction reduces
      exposure, it does not make real incident data safe to share.

## 3. Job store scaling

`find_live_job` and `list_jobs` parse every `job.json` on each call, and
`start_analysis` / `investigate` / `resume` all call them.

- [ ] Track the live job with a single lock file under `outputs/jobs/` instead
      of scanning, and clear it in the same paths that set a terminal state.
- [ ] Make `recover_interrupted_jobs` remove a stale lock at startup.
- [ ] Add pagination (`limit` / `cursor`) to `incident_lab_list_analysis_jobs`.
- [ ] Decide on retention: document that old jobs accumulate, or add a CLI
      `prune` command that lists what it would remove before removing anything.

## 4. CI housekeeping

- [ ] Stop `Verify` running twice per PR: limit the `push` trigger to `main`.
- [ ] Add a `pip-audit` step against the locked requirements
      (`uv export --locked` → `pip-audit --require-hashes`).
- [ ] Add a guard test that fails if any collected test ID is longer than
      ~200 characters, so the Windows `PYTEST_CURRENT_TEST` hang cannot return.
- [ ] Once `Verify` has been green for a while, consider requiring it on `main`.
      Leave reviews unrequired — this is a solo-maintained repo.

## 5. Smaller hardening items

- [ ] Cap `incident.json` size before parsing it (evidence files are bounded;
      the manifest itself is not).
- [ ] Validate `file_ids` / `ranges` list lengths in `incident_lab_start_analysis`.
- [ ] Create `outputs/jobs` and `outputs/reports` owner-only too, for output
      folders that were created before setup started using `0700`.
- [ ] Prune old `*.bak-*` copies written by `onboarding.write_json`, keeping the
      most recent few. The Claude Desktop config backups can contain other
      servers' environment values.
- [ ] Trim pydantic error text in `MANIFEST_INVALID` so it reports field names
      and error types without echoing input values.

## 6. Repository housekeeping

- [ ] Decide what to do with the `origin` remote
      (`bruce-hoppe_uoft/sap-incident-lab` returns "Repository not found").
      `main` now tracks `personal`; `origin` was left in place deliberately.
- [ ] Delete the merged `review/security-hardening` branch on GitHub.
- [ ] Optional: `gh auth refresh -s workflow` for the `brucehoppe` account. SSH
      pushes already work; this only matters for HTTPS/API pushes that touch
      `.github/workflows/`.
- [ ] Cut a release once items 1 and 2 land (`docs/release.md`,
      `scripts/release.sh`).
