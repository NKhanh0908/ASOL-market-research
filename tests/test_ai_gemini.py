"""Offline contract tests for the one-call Gemini pilot adapter."""

from __future__ import annotations

import json
import os

import httpx
import pytest

from casual_scout.ai.gemini import GeminiProvider
from casual_scout.ai.provider import ProviderFailure, ProviderQuota, ProviderTimeout
from casual_scout.ai.settings import AISettings, load_ai_runtime

KEY = "dummy-test-key"
URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
FROZEN = {
    "system_prompt": "Persisted instruction exactly",
    "user_evidence_json": '{"analysis_date":"2026-09-25","candidates":[]}',
    "output_schema": {"type": "object", "properties": {"schema_version": {"type": "string"}}},
    "max_output_tokens": 2000,
}


def _response(*, text='{"schema_version":"1","recommendations":[]}',
              finish="STOP", usage=None, parts=None):
    return {
        "candidates": [{"content": {"parts": parts if parts is not None else [{"text": text}]},
                        "finishReason": finish}],
        "usageMetadata": usage if usage is not None else {
            "promptTokenCount": 12, "candidatesTokenCount": 4, "totalTokenCount": 16,
        },
    }


def test_one_bounded_request_uses_frozen_prompt_evidence_and_schema():
    seen = []

    def handle(request):
        seen.append(request)
        assert request.method == "POST"
        assert str(request.url) == URL
        assert request.headers["x-goog-api-key"] == KEY
        body = json.loads(request.content)
        assert body == {
            "systemInstruction": {"parts": [{"text": FROZEN["system_prompt"]}]},
            "contents": [{"role": "user", "parts": [{"text": FROZEN["user_evidence_json"]}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": FROZEN["output_schema"],
                "candidateCount": 1,
                "maxOutputTokens": 2000,
            },
        }
        return httpx.Response(200, json=_response())

    provider = GeminiProvider(KEY, timeout_seconds=7, transport=httpx.MockTransport(handle))
    assert (provider.provider_id, provider.model_id) == ("gemini", "gemini-2.5-flash")
    assert provider.estimate_cost(FROZEN) is None
    reply = provider.complete(FROZEN)
    assert reply.output == {"schema_version": "1", "recommendations": []}
    assert reply.usage == {"input_tokens": 12, "output_tokens": 4, "total_tokens": 16}
    assert reply.actual_cost_usd is None and reply.cost_method is None
    assert len(seen) == 1
    assert seen[0].extensions["timeout"]["read"] == 7


def test_redirect_is_not_followed_and_key_never_appears_in_errors():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://example.org/redirect"})

    provider = GeminiProvider(KEY, transport=httpx.MockTransport(handle))
    with pytest.raises(ProviderFailure) as caught:
        provider.complete(FROZEN)
    assert len(calls) == 1
    assert KEY not in repr(provider) + repr(caught.value) + str(caught.value)


@pytest.mark.parametrize("status,error_type", [
    (429, ProviderQuota), (401, ProviderFailure), (403, ProviderFailure),
    (500, ProviderFailure),
])
def test_http_errors_are_safe_and_terminal(status, error_type):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "secret raw provider error"},
                                            "usageMetadata": {"promptTokenCount": 3}})

    with pytest.raises(error_type) as caught:
        GeminiProvider(KEY, transport=httpx.MockTransport(handle)).complete(FROZEN)
    assert len(calls) == 1
    assert caught.value.usage == {"input_tokens": 3}
    assert "secret raw" not in str(caught.value)


def test_timeout_is_safe_and_not_retried():
    calls = []

    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout("secret transport detail")

    with pytest.raises(ProviderTimeout) as caught:
        GeminiProvider(KEY, transport=httpx.MockTransport(handle)).complete(FROZEN)
    assert len(calls) == 1
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize("response,expected_usage", [
    (httpx.Response(200, content=b"not json"), None),
    (httpx.Response(200, json={"candidates": [], "usageMetadata": {"totalTokenCount": 9}}),
     {"total_tokens": 9}),
    (httpx.Response(200, json=_response(text="{bad json", usage={"promptTokenCount": 7,
                                                                  "candidatesTokenCount": True,
                                                                  "raw": "secret"})),
     {"input_tokens": 7}),
    (httpx.Response(200, json=_response(finish="MAX_TOKENS", usage={"totalTokenCount": 8})),
     {"total_tokens": 8}),
])
def test_malformed_or_truncated_output_fails_with_only_safe_usage(response, expected_usage):
    with pytest.raises(ProviderFailure) as caught:
        GeminiProvider(KEY, transport=httpx.MockTransport(lambda _: response)).complete(FROZEN)
    assert "secret" not in str(caught.value)
    assert caught.value.usage == expected_usage


def test_thought_parts_are_excluded_from_output():
    parts = [{"text": "ignore thought", "thought": True},
             {"text": '{"schema_version":"1","recommendations":[]}'}]
    response = httpx.Response(200, json=_response(parts=parts))
    reply = GeminiProvider(KEY, transport=httpx.MockTransport(lambda _: response)).complete(FROZEN)
    assert reply.output == {"schema_version": "1", "recommendations": []}


def test_reported_thinking_and_cache_tokens_are_preserved_without_invented_zeros():
    response = httpx.Response(200, json=_response(usage={
        "promptTokenCount": 12, "candidatesTokenCount": 4, "totalTokenCount": 25,
        "thoughtsTokenCount": 9, "cachedContentTokenCount": 2,
    }))
    reply = GeminiProvider(KEY, transport=httpx.MockTransport(lambda _: response)).complete(FROZEN)
    assert reply.usage == {
        "input_tokens": 12, "output_tokens": 4, "total_tokens": 25,
        "reasoning_tokens": 9, "cached_tokens": 2,
    }


@pytest.mark.parametrize("cap", [0, 2001, True])
def test_invalid_token_cap_never_sends_request(cap):
    calls = []
    provider = GeminiProvider(KEY, transport=httpx.MockTransport(lambda request: calls.append(request)))
    with pytest.raises(ProviderFailure):
        provider.complete({**FROZEN, "max_output_tokens": cap})
    assert calls == []


def test_runtime_env_overrides_dotenv_without_mutating_process(tmp_path, monkeypatch):
    for name in (
        "GEMINI_API_KEY", "CASUAL_SCOUT_AI_ENABLED", "CASUAL_SCOUT_AI_MAX_COST_USD",
        "CASUAL_SCOUT_AI_MAX_OUTPUT_TOKENS", "CASUAL_SCOUT_AI_TIMEOUT_SECONDS",
        "CASUAL_SCOUT_AI_CONFIRM_UNKNOWN_COST", "CASUAL_SCOUT_AI_COST_MODE",
        "CASUAL_SCOUT_AI_FREE_TIER_CONFIRMED", "CASUAL_SCOUT_AI_MAX_RUNS_PER_DAY",
    ):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GEMINI_API_KEY=dummy-file-key\nCASUAL_SCOUT_AI_ENABLED=true\n"
        "CASUAL_SCOUT_AI_COST_MODE=free_tier\n"
        "CASUAL_SCOUT_AI_FREE_TIER_CONFIRMED=true\n"
        "CASUAL_SCOUT_AI_CONFIRM_UNKNOWN_COST=true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    monkeypatch.delenv("CASUAL_SCOUT_AI_ENABLED", raising=False)
    monkeypatch.delenv("CASUAL_SCOUT_AI_COST_MODE", raising=False)
    monkeypatch.delenv("CASUAL_SCOUT_AI_FREE_TIER_CONFIRMED", raising=False)
    monkeypatch.delenv("CASUAL_SCOUT_AI_CONFIRM_UNKNOWN_COST", raising=False)
    settings, provider = load_ai_runtime(env_file)
    assert settings == AISettings(enabled=True, cost_mode="free_tier",
                                  free_tier_confirmed=True,
                                  allow_unknown_cost_confirmation=True)
    assert provider is not None
    assert KEY not in repr(settings) + repr(provider)
    assert "CASUAL_SCOUT_AI_ENABLED" not in os.environ
    assert os.environ["GEMINI_API_KEY"] == KEY
    seen = []

    def handle(request):
        seen.append(request.headers["x-goog-api-key"])
        return httpx.Response(200, json=_response())

    provider._transport = httpx.MockTransport(handle)
    provider.complete(FROZEN)
    assert seen == [KEY]


@pytest.mark.parametrize("line", [
    "GEMINI_API_KEY=", "CASUAL_SCOUT_AI_MAX_OUTPUT_TOKENS=2001",
    "CASUAL_SCOUT_AI_TIMEOUT_SECONDS=0", "CASUAL_SCOUT_AI_MAX_RUNS_PER_DAY=4",
    "CASUAL_SCOUT_AI_FREE_TIER_CONFIRMED=false",
])
def test_missing_or_invalid_local_configuration_disables_provider(tmp_path, monkeypatch, line):
    for name in ("GEMINI_API_KEY", "CASUAL_SCOUT_AI_ENABLED", "CASUAL_SCOUT_AI_COST_MODE",
                 "CASUAL_SCOUT_AI_FREE_TIER_CONFIRMED", "CASUAL_SCOUT_AI_CONFIRM_UNKNOWN_COST",
                 "CASUAL_SCOUT_AI_MAX_OUTPUT_TOKENS", "CASUAL_SCOUT_AI_TIMEOUT_SECONDS",
                 "CASUAL_SCOUT_AI_MAX_RUNS_PER_DAY"):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "GEMINI_API_KEY=dummy-file-key\nCASUAL_SCOUT_AI_ENABLED=true\n"
        "CASUAL_SCOUT_AI_COST_MODE=free_tier\n"
        "CASUAL_SCOUT_AI_FREE_TIER_CONFIRMED=true\n"
        f"CASUAL_SCOUT_AI_CONFIRM_UNKNOWN_COST=true\n{line}\n",
        encoding="utf-8",
    )
    settings, provider = load_ai_runtime(env_file)
    assert provider is None
    assert settings.enabled is False
