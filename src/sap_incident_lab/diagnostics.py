from __future__ import annotations

import tempfile
from typing import Any

import httpx

from .analysis.ollama_client import extract_with_repair
from .config import Settings
from .errors import ToolError


async def ollama_health(settings: Settings) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            response = await client.get(f"{settings.ollama_url.rstrip('/')}/api/tags")
            response.raise_for_status()
            body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get("models"), list):
            raise ValueError("Invalid model inventory")
        names = [
            item["name"]
            for item in body["models"]
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
        model = settings.model if ":" in settings.model else settings.model + ":latest"
        installed = model in names or settings.model in names
        return {
            "ollama_reachable": True,
            "configured_model": settings.model,
            "model_installed": installed,
            "next_step": None
            if installed
            else f"Run ollama pull {settings.model}, then run doctor again.",
        }
    except (httpx.HTTPError, ValueError) as exc:
        return {
            "ollama_reachable": False,
            "configured_model": settings.model,
            "model_installed": False,
            "error_type": type(exc).__name__,
            "next_step": "Start Ollama, then run sap-incident-lab doctor again.",
        }


async def doctor(settings: Settings, *, extraction: bool = True) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    reason = settings.evidence_config_error()
    checks.append(
        {
            "name": "configuration",
            "ok": reason is None,
            "detail": reason or "Evidence and output folders are separate.",
            "next_step": "Run sap-incident-lab setup." if reason else None,
        }
    )
    if reason is None:
        assert settings.root is not None and settings.output is not None
        try:
            # Test actual access, not only permission bits.
            next(settings.root.iterdir(), None)
            settings.output.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=settings.output) as handle:
                handle.write(b"doctor")
                handle.flush()
            checks.append(
                {
                    "name": "folder_access",
                    "ok": True,
                    "detail": "Evidence folder listable; output writable.",
                }
            )
        except OSError:
            checks.append(
                {
                    "name": "folder_access",
                    "ok": False,
                    "detail": "Evidence cannot be listed or output cannot be written.",
                    "next_step": "Choose accessible folders with setup --data-dir, or fix their permissions.",
                }
            )
    health = await ollama_health(settings)
    checks.append(
        {
            "name": "ollama_model",
            "ok": health["ollama_reachable"] and health["model_installed"],
            "detail": (
                f"Ollama is reachable; {settings.model} is installed."
                if health["model_installed"]
                else f"Model {settings.model} is not installed."
                if health["ollama_reachable"]
                else "Ollama could not be reached."
            ),
            "status": health,
            "next_step": health["next_step"],
        }
    )
    if extraction and health["ollama_reachable"] and health["model_installed"]:
        try:
            result, _ = await extract_with_repair(
                settings,
                question="What was observed?",
                file_id="demo",
                start_line=1,
                end_line=2,
                lines=["Synthetic connection attempt timed out.", "The retry succeeded."],
            )
            checks.append(
                {
                    "name": "extraction",
                    "ok": result.status == "completed",
                    "detail": result.status,
                    "next_step": None
                    if result.status == "completed"
                    else "Check the model with ollama run, then retry doctor; truncated output may need a larger num_predict.",
                }
            )
        except ToolError as exc:
            checks.append(
                {
                    "name": "extraction",
                    "ok": False,
                    "detail": exc.message,
                    "next_step": exc.recovery,
                }
            )
    elif extraction:
        checks.append(
            {
                "name": "extraction",
                "ok": False,
                "detail": "Not run until Ollama and the model are ready.",
            }
        )
    return {
        "ready": all(check["ok"] for check in checks),
        "extraction_tested": extraction
        and any(check["name"] == "extraction" and check["ok"] for check in checks),
        "checks": checks,
        "next_step": "Run sap-incident-lab demo, then investigate INC-DEMO-001 in Claude."
        if all(c["ok"] for c in checks)
        else "Follow the failed checks above, then run doctor again.",
    }
