"""Presentation helpers for multi-platform web UI and badge rendering."""
from __future__ import annotations

from urllib.parse import urlencode


def installs_badge(min_installs: int | None) -> tuple[str, str]:
    """Return display label and CSS class for Android minimum install count."""
    if min_installs is None:
        return "Chưa có dữ liệu", "installs-unknown"
    if min_installs >= 50_000_000:
        return "💎 50M+", "installs-global"
    if min_installs >= 10_000_000:
        return "🔥 10M+", "installs-popular"
    if min_installs >= 1_000_000:
        return "⚡ 1M+", "installs-growing"
    if min_installs >= 100_000:
        return "🌱 100K+", "installs-emerging"
    return "👀 <100K", "installs-small"


def render_installs_badge(min_installs: int | None) -> str:
    """Return ready-to-render HTML span for installs badge."""
    label, cls = installs_badge(min_installs)
    return f'<span class="installs-badge {cls}">{label}</span>'


def platform_url(path: str, query: dict, platform: str) -> str:
    """Build a URL preserving current filters while switching platform and removing snapshot_id."""
    clean_query = dict(query)
    clean_query["platform"] = platform
    clean_query.pop("snapshot_id", None)
    encoded = urlencode(clean_query)
    return f"{path}?{encoded}" if encoded else path


def app_store_url(store_url: str | None, app_id: str, platform: str = "ios", country: str = "vn") -> str:
    """Return valid store URL for iOS or Android."""
    if store_url:
        return store_url
    if platform == "android":
        return f"https://play.google.com/store/apps/details?id={app_id}&hl=en&gl={country}"
    return f"https://apps.apple.com/{country}/app/id{app_id}"
