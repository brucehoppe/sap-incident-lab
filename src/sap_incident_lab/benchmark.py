from __future__ import annotations

import platform
from datetime import UTC, datetime
from importlib.metadata import version
from typing import Any

from .analysis.ollama_client import extract_once
from .config import Settings


async def benchmark_models(settings: Settings, models: list[str], repeats: int = 1) -> dict[str, Any]:
    """Run a small, bounded extraction probe for each explicitly selected model."""
    results: list[dict[str, Any]] = []
    for model in models:
        runs: list[dict[str, Any]] = []
        for _ in range(repeats):
            try:
                result = await extract_once(
                    settings, model=model, question="What was observed in this synthetic log?",
                    file_id="benchmark", start_line=1, end_line=2,
                    lines=["10:00 RFC connection failed with timeout.", "10:01 Retry succeeded."],
                )
                runs.append({"status": result.status, "elapsed_seconds": round(result.elapsed_seconds, 3), "model_used": result.model_used})
            except Exception as exc:  # benchmark reports model-specific failures side by side
                runs.append({"status": "error", "error_type": type(exc).__name__})
        completed = [run for run in runs if run["status"] == "completed"]
        results.append({
            "model": model, "runs": runs, "completed": len(completed),
            "average_seconds": round(sum(run["elapsed_seconds"] for run in completed) / len(completed), 3) if completed else None,
        })
    return {
        "app_version": version("sap-incident-lab"),
        "created_at": datetime.now(UTC).isoformat(),
        "platform": platform.platform(),
        "context": settings.num_ctx,
        "max_prediction": settings.num_predict,
        "models": results,
        "repeats": repeats,
        "request": "structured extraction",
    }
