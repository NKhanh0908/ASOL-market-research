"""Server-side, disabled-by-default AI evaluation policy."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from casual_scout.ai.gemini import GeminiProvider


@dataclass(frozen=True)
class AISettings:
    enabled: bool = False
    max_cost_per_run_usd: str | None = None
    max_output_tokens: int = 2000
    timeout_seconds: int = 60
    allow_unknown_cost_confirmation: bool = False
    cost_mode: str = "metered"
    free_tier_confirmed: bool = False
    max_runs_per_day: int = 5


def _boolean(value: str | None) -> bool:
    return value is not None and value.strip().casefold() in {"true", "1", "yes"}


def _integer(value: str | None, default: int) -> int:
    try:
        return default if value is None else int(value)
    except ValueError:
        return 0  # Invalid settings fail the preflight bounds.


def load_ai_settings(environ: Mapping[str, str] | None = None) -> AISettings:
    """Parse a supplied mapping, or only the process environment by default."""
    values = os.environ if environ is None else environ
    return AISettings(
        enabled=_boolean(values.get("CASUAL_SCOUT_AI_ENABLED")),
        max_cost_per_run_usd=values.get("CASUAL_SCOUT_AI_MAX_COST_USD"),
        max_output_tokens=_integer(values.get("CASUAL_SCOUT_AI_MAX_OUTPUT_TOKENS"), 2000),
        timeout_seconds=_integer(values.get("CASUAL_SCOUT_AI_TIMEOUT_SECONDS"), 60),
        allow_unknown_cost_confirmation=_boolean(values.get("CASUAL_SCOUT_AI_CONFIRM_UNKNOWN_COST")),
        cost_mode=values.get("CASUAL_SCOUT_AI_COST_MODE", "metered"),
        free_tier_confirmed=_boolean(values.get("CASUAL_SCOUT_AI_FREE_TIER_CONFIRMED")),
        max_runs_per_day=_integer(values.get("CASUAL_SCOUT_AI_MAX_RUNS_PER_DAY"), 5),
    )


def _dotenv_values(path: Path) -> dict[str, str]:
    """Read a local dotenv file without exporting values to the process."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except FileNotFoundError:
        return {}
    values = {}
    for line in lines:
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if entry.startswith("export "):
            entry = entry[7:].lstrip()
        if "=" not in entry:
            continue
        name, value = entry.split("=", 1)
        name = name.strip()
        if not name or not (name.replace("_", "a").isalnum() and not name[0].isdigit()):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[name] = value
    return values


def load_ai_runtime(env_path: Path | None = None) -> tuple[AISettings, GeminiProvider | None]:
    """Explicit server-startup loading; environment overrides the local dotenv file."""
    try:
        values = _dotenv_values(Path.cwd() / ".env" if env_path is None else env_path)
    except (OSError, UnicodeError):
        return AISettings(), None
    for name in (
        "GEMINI_API_KEY", "CASUAL_SCOUT_AI_ENABLED", "CASUAL_SCOUT_AI_MAX_COST_USD",
        "CASUAL_SCOUT_AI_MAX_OUTPUT_TOKENS", "CASUAL_SCOUT_AI_TIMEOUT_SECONDS",
        "CASUAL_SCOUT_AI_CONFIRM_UNKNOWN_COST", "CASUAL_SCOUT_AI_COST_MODE",
        "CASUAL_SCOUT_AI_FREE_TIER_CONFIRMED", "CASUAL_SCOUT_AI_MAX_RUNS_PER_DAY",
    ):
        if name in os.environ:
            values[name] = os.environ[name]
    settings = load_ai_settings(values)
    key = values.get("GEMINI_API_KEY")
    if not settings.enabled:
        return settings, None
    if (settings.cost_mode != "free_tier" or not settings.free_tier_confirmed
            or not settings.allow_unknown_cost_confirmation
            or settings.max_runs_per_day != 5
            or not 1 <= settings.max_output_tokens <= 2000
            or settings.timeout_seconds <= 0 or not key):
        return replace(settings, enabled=False), None
    try:
        provider = GeminiProvider(key, timeout_seconds=settings.timeout_seconds)
    except ValueError:
        return replace(settings, enabled=False), None
    return settings, provider
