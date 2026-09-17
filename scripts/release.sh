#!/usr/bin/env bash
set -euo pipefail

# Build a release candidate and leave a checksummed, consumer-testable folder
# under dist. Run this from a clean checkout with uv installed.
uv sync --locked --extra dev
uv run pytest
uv run ruff check src tests scripts
uv run mypy src
uv build

version="$(uv run python -c 'from importlib.metadata import version; print(version("sap-incident-lab"))')"
release_dir="dist/sap-incident-lab-${version}"
mkdir -p "${release_dir}"
find dist -maxdepth 1 -type f \( -name 'sap_incident_lab-*.whl' -o -name 'sap_incident_lab-*.tar.gz' \) -exec cp {} "${release_dir}/" \;

wheel="$(find "${release_dir}" -name '*.whl' -print -quit)"
uv run python scripts/consumer-check.py "${wheel}"
uv run python scripts/sbom.py > "${release_dir}/SBOM.cdx.json"
(cd "${release_dir}" && shasum -a 256 * > SHA256SUMS.txt)
printf 'Release candidate: %s\n' "${release_dir}"
