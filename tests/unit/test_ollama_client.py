from __future__ import annotations

import json

import httpx
import pytest

from sap_incident_lab import errors
from sap_incident_lab.analysis.ollama_client import extract_once, extract_with_repair
from sap_incident_lab.analysis.schemas import ModelExtraction
from sap_incident_lab.config import Settings

VALID_BODY = {
    "done_reason": "stop",
    "message": {
        "content": json.dumps(
            ModelExtraction(
                observations=[], hypotheses=[], timeline=[], search_terms=[], missing_information=[]
            ).model_dump()
        )
    },
}


def _settings_with_transport(monkeypatch: pytest.MonkeyPatch, handler) -> Settings:
    """Point httpx.AsyncClient at a MockTransport for this test only."""
    real_client = httpx.AsyncClient

    def patched(*args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr("sap_incident_lab.analysis.ollama_client.httpx.AsyncClient", patched)
    return Settings()


@pytest.mark.asyncio
async def test_extract_once_parses_a_valid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=VALID_BODY)

    settings = _settings_with_transport(monkeypatch, handler)
    result = await extract_once(
        settings, question="what happened?", file_id="f01", start_line=1, end_line=2, lines=["a", "b"]
    )
    assert result.status == "completed"
    assert result.extraction is not None


@pytest.mark.asyncio
async def test_extract_once_reports_truncated_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"done_reason": "length", "message": {"content": "{"}})

    settings = _settings_with_transport(monkeypatch, handler)
    result = await extract_once(
        settings, question="q", file_id="f01", start_line=1, end_line=1, lines=["a"]
    )
    assert result.status == "truncated_output"
    assert result.extraction is None


@pytest.mark.asyncio
async def test_extract_once_reports_invalid_json_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"done_reason": "stop", "message": {"content": "not json"}})

    settings = _settings_with_transport(monkeypatch, handler)
    result = await extract_once(
        settings, question="q", file_id="f01", start_line=1, end_line=1, lines=["a"]
    )
    assert result.status == "invalid_output"


@pytest.mark.asyncio
async def test_unreachable_ollama_raises_tool_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    settings = _settings_with_transport(monkeypatch, handler)
    with pytest.raises(errors.ToolError) as excinfo:
        await extract_once(settings, question="q", file_id="f01", start_line=1, end_line=1, lines=["a"])
    assert excinfo.value.code == "OLLAMA_UNAVAILABLE"


@pytest.mark.asyncio
async def test_missing_primary_uses_configured_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        model = json.loads(request.content)["model"]
        calls.append(model)
        if model == "primary":
            return httpx.Response(404, json={"error": "model not found"})
        return httpx.Response(200, json=VALID_BODY)

    settings = _settings_with_transport(monkeypatch, handler).model_copy(
        update={"model": "primary", "fallback_model": "fallback"}
    )
    result, repaired = await extract_with_repair(
        settings, question="q", file_id="f01", start_line=1, end_line=1, lines=["a"]
    )
    assert calls == ["primary", "fallback"]
    assert result.status == "completed"
    assert result.model_used == "fallback"
    assert repaired is False


@pytest.mark.asyncio
async def test_repair_is_attempted_exactly_once_on_invalid_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        is_repair = "previous response was not valid" in body["messages"][1]["content"]
        calls.append("repair" if is_repair else "initial")
        if is_repair:
            return httpx.Response(200, json=VALID_BODY)
        return httpx.Response(200, json={"done_reason": "stop", "message": {"content": "garbage"}})

    settings = _settings_with_transport(monkeypatch, handler)
    result, repaired = await extract_with_repair(
        settings, question="q", file_id="f01", start_line=1, end_line=1, lines=["a"]
    )
    assert calls == ["initial", "repair"]
    assert repaired is True
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_no_repair_attempted_when_first_response_is_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=VALID_BODY)

    settings = _settings_with_transport(monkeypatch, handler)
    _result, repaired = await extract_with_repair(
        settings, question="q", file_id="f01", start_line=1, end_line=1, lines=["a"]
    )
    assert calls == 1
    assert repaired is False


@pytest.mark.asyncio
async def test_no_repair_attempted_on_truncated_output(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"done_reason": "length", "message": {"content": "{"}})

    settings = _settings_with_transport(monkeypatch, handler)
    result, repaired = await extract_with_repair(
        settings, question="q", file_id="f01", start_line=1, end_line=1, lines=["a"]
    )
    assert calls == 1
    assert repaired is False
    assert result.status == "truncated_output"


@pytest.mark.parametrize("body", [b"not JSON", b"null", b"[]", b'{"message": null}', b'{"message": {"content": 123}}'])
async def test_malformed_response_envelopes_are_invalid_output(monkeypatch, body) -> None:
    settings = _settings_with_transport(
        monkeypatch, lambda request: httpx.Response(200, content=body)
    )
    result, repaired = await extract_with_repair(
        settings, question="q", file_id="f01", start_line=1, end_line=1, lines=["a"]
    )
    assert result.status == "invalid_output"
    assert repaired
