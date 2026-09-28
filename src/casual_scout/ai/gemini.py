"""One-request Gemini Developer API adapter for the manual P4 pilot."""

from __future__ import annotations

import json
from typing import Any

import httpx

from casual_scout.ai.contracts import ProviderReply
from casual_scout.ai.provider import ProviderFailure, ProviderQuota, ProviderTimeout

_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent")
_USAGE_FIELDS = {
    "promptTokenCount": "input_tokens",
    "candidatesTokenCount": "output_tokens",
    "totalTokenCount": "total_tokens",
    "thoughtsTokenCount": "reasoning_tokens",
    "cachedContentTokenCount": "cached_tokens",
}


def _safe_usage(payload: Any) -> dict[str, int] | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("usageMetadata"), dict):
        return None
    metadata = payload["usageMetadata"]
    usage = {target: value for source, target in _USAGE_FIELDS.items()
             if type(value := metadata.get(source)) is int and value >= 0}
    return usage or None


class GeminiProvider:
    """Call the fixed Flash model once and return only parsed JSON and safe usage."""

    provider_id = "gemini"
    model_id = "gemini-2.5-flash"

    def __init__(self, api_key: str, *, timeout_seconds: int = 60,
                 transport: httpx.BaseTransport | None = None) -> None:
        if (not isinstance(api_key, str) or not api_key or api_key.strip() != api_key
                or any(ord(char) < 33 or ord(char) > 126 for char in api_key)):
            raise ValueError("invalid Gemini API key")
        if type(timeout_seconds) is not int or timeout_seconds <= 0:
            raise ValueError("invalid Gemini timeout")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def estimate_cost(self, canonical_input: dict[str, Any]) -> None:
        """Gemini usage metadata is not a monetary estimate or invoice."""

    def complete(self, canonical_input: dict[str, Any]) -> ProviderReply:
        try:
            prompt = canonical_input["system_prompt"]
            evidence = canonical_input["user_evidence_json"]
            schema = canonical_input["output_schema"]
            cap = canonical_input["max_output_tokens"]
            if (not isinstance(prompt, str) or not prompt
                    or not isinstance(evidence, str) or not evidence
                    or not isinstance(schema, dict) or not schema
                    or type(cap) is not int or not 1 <= cap <= 2000):
                raise ProviderFailure()
            body = {
                "systemInstruction": {"parts": [{"text": prompt}]},
                "contents": [{"role": "user", "parts": [{"text": evidence}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseJsonSchema": schema,
                    "candidateCount": 1,
                    "maxOutputTokens": cap,
                },
            }
            with httpx.Client(timeout=httpx.Timeout(self._timeout_seconds),
                              follow_redirects=False, transport=self._transport) as client:
                response = client.post(_URL, headers={"x-goog-api-key": self._api_key}, json=body)
        except ProviderFailure:
            raise
        except httpx.TimeoutException:
            raise ProviderTimeout() from None
        except Exception:  # noqa: BLE001 - never expose transport detail or key
            raise ProviderFailure() from None

        try:
            payload = response.json()
        except (ValueError, UnicodeError):
            payload = None
        usage = _safe_usage(payload)
        if response.status_code == 429:
            raise ProviderQuota(usage)
        if response.status_code != 200 or not isinstance(payload, dict):
            raise ProviderFailure(usage)
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 1:
            raise ProviderFailure(usage)
        candidate = candidates[0]
        if not isinstance(candidate, dict) or candidate.get("finishReason") != "STOP":
            raise ProviderFailure(usage)
        content = candidate.get("content")
        parts = content.get("parts") if isinstance(content, dict) else None
        if not isinstance(parts, list) or not parts:
            raise ProviderFailure(usage)
        texts = []
        for part in parts:
            if not isinstance(part, dict):
                raise ProviderFailure(usage)
            if part.get("thought") is True:
                continue
            if not isinstance(part.get("text"), str):
                raise ProviderFailure(usage)
            texts.append(part["text"])
        if not texts:
            raise ProviderFailure(usage)
        try:
            output = json.loads("".join(texts))
        except (ValueError, UnicodeError):
            raise ProviderFailure(usage) from None
        if not isinstance(output, dict):
            raise ProviderFailure(usage)
        return ProviderReply(output=output, usage=usage)
