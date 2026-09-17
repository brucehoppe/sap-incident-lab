"""Run the bounded extraction evaluator against the four synthetic cases."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from sap_incident_lab.analysis.ollama_client import extract_with_repair
from sap_incident_lab.config import Settings
from sap_incident_lab.evidence.registry import load_files

EXPECTED = {
    "INC-SYN-001": ("enqueue lock", ("enqueue", "lock")),
    "INC-SYN-002": ("pagination loop", ("start_matnr", "unchanged")),
    "INC-SYN-003": ("unbounded buffer", ("it_material_buffer", "tsv_tnew_page_alloc_failed")),
    "INC-SYN-004": ("expired certificate", ("syn_client_cert", "expiry")),
}


async def evaluate(model: str, fixtures: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="sap-incident-eval-") as directory:
        root = Path(directory) / "incidents"
        output = Path(directory) / "outputs"
        root.mkdir()
        output.mkdir()
        for incident_id in EXPECTED:
            shutil.copytree(fixtures / incident_id, root / incident_id,
                            ignore=shutil.ignore_patterns("evaluation-private.md"))
        settings = Settings(root=root, output=output, model=model)
        cases = []
        for incident_id, (label, required) in EXPECTED.items():
            _manifest, records = load_files(settings, incident_id)
            texts: list[str] = []
            statuses: list[str] = []
            invalid_refs = 0
            for record in records:
                result, repaired = await extract_with_repair(
                    settings, question="Identify the important observations and missing information.",
                    file_id=record.file_id, start_line=1, end_line=record.line_count,
                    lines=record.lines,
                )
                statuses.append(result.status)
                if result.extraction:
                    texts.extend(obs.text for obs in result.extraction.observations)
                    invalid_refs += sum(
                        1 for obs in result.extraction.observations
                        for ref in obs.refs
                        if not (1 <= ref.start_line <= ref.end_line <= record.line_count)
                    )
            combined = "\n".join(texts).casefold()
            found = [term for term in required if term in combined]
            cases.append({
                "incident_id": incident_id, "label": label, "model": model,
                "statuses": statuses, "required_terms": list(required), "found_terms": found,
                "pass": len(found) == len(required) and all(s == "completed" for s in statuses),
                "invalid_refs": invalid_refs,
            })
        return {"model": model, "cases": cases,
                "passed": sum(bool(case["pass"]) for case in cases), "total": len(cases)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3.5:9b")
    parser.add_argument("--fixtures", type=Path, default=Path(__file__).parents[1] / "tests/fixtures")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(evaluate(args.model, args.fixtures.resolve()))
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.expanduser().resolve().write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    raise SystemExit(0 if result["passed"] == result["total"] else 1)


if __name__ == "__main__":
    main()
