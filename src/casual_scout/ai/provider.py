"""Provider boundary for one manual, non-retried evaluation call."""

from __future__ import annotations

from typing import Any, Protocol

from casual_scout.ai.contracts import ProviderReply


class Provider(Protocol):
    provider_id: str
    model_id: str

    def estimate_cost(self, canonical_input: dict[str, Any]) -> str | None: ...

    def complete(self, canonical_input: dict[str, Any]) -> ProviderReply: ...


class ProviderTimeout(RuntimeError):
    """The call timed out and its billing outcome is uncertain."""

    def __init__(self) -> None:
        super().__init__("provider timeout")


class ProviderQuota(RuntimeError):
    """The provider rejected this call for quota or rate limits."""

    def __init__(self, usage: dict[str, Any] | None = None) -> None:
        super().__init__("provider quota")
        self.usage = usage


class ProviderFailure(RuntimeError):
    """The provider failed; only whitelisted usage may be retained."""

    def __init__(self, usage: dict[str, Any] | None = None) -> None:
        super().__init__("provider failure")
        self.usage = usage
