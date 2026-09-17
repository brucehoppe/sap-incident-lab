from __future__ import annotations

import json
import tomllib
from pathlib import Path

lock = tomllib.loads(Path("uv.lock").read_text(encoding="utf-8"))
components = []
for package in lock.get("package", []):
    if isinstance(package, dict) and isinstance(package.get("name"), str) and isinstance(package.get("version"), str):
        components.append({"type": "library", "name": package["name"], "version": package["version"]})
print(json.dumps({
    "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
    "components": sorted(components, key=lambda item: item["name"]),
}, indent=2))
