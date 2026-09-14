from __future__ import annotations

import httpx
import pytest

from sap_incident_lab.config import Settings
from sap_incident_lab.diagnostics import doctor, ollama_health


def patch_http(monkeypatch, handler) -> None:
    real = httpx.AsyncClient

    def patched(*args, **kwargs):
        return real(*args, **{**kwargs, "transport": httpx.MockTransport(handler)})

    monkeypatch.setattr("httpx.AsyncClient", patched)


async def test_doctor_exercises_extraction(settings: Settings, monkeypatch) -> None:
    requests = []

    def handler(request):
        requests.append(request.url.path)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": settings.model}]})
        return httpx.Response(200, json={"message": {"content": '{"observations": []}'}})

    patch_http(monkeypatch, handler)
    result = await doctor(settings)
    assert result["ready"]
    assert result["extraction_tested"]
    assert requests == ["/api/tags", "/api/chat"]


async def test_doctor_missing_model_gives_pull_command(settings: Settings, monkeypatch) -> None:
    patch_http(monkeypatch, lambda request: httpx.Response(200, json={"models": []}))
    result = await doctor(settings)
    assert not result["ready"]
    assert not result["extraction_tested"]
    model_check = next(c for c in result["checks"] if c["name"] == "ollama_model")
    assert f"ollama pull {settings.model}" in model_check["next_step"]


@pytest.mark.parametrize("body", [None, [], {"models": None}])
async def test_health_handles_malformed_inventory(settings: Settings, monkeypatch, body) -> None:
    patch_http(monkeypatch, lambda request: httpx.Response(200, json=body))
    result = await ollama_health(settings)
    assert not result["ollama_reachable"]
    assert result["next_step"]


async def test_doctor_unreachable_is_actionable(settings: Settings, monkeypatch) -> None:
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    patch_http(monkeypatch, handler)
    result = await doctor(settings)
    assert not result["ready"]
    assert "Start Ollama" in result["checks"][-2]["next_step"]
