# Release procedure

Run from a clean checkout:

```sh
UV_CACHE_DIR=/private/tmp/sap-incident-lab-uv-cache ./scripts/release.sh
```

The script runs tests, Ruff, strict mypy, builds the wheel and source
distribution, performs a fresh consumer/stdio check, emits a CycloneDX SBOM,
and writes SHA-256 checksums under `dist/sap-incident-lab-VERSION/`.

Before publishing externally, also run a current dependency audit in an
internet-enabled environment, review the generated SBOM, inspect the archive
contents for secrets and private data, create a signed Git tag/GitHub release,
and complete native Windows plus approved-client acceptance. These checks are
not replaced by local mocked tests or cross-platform CI definitions.
