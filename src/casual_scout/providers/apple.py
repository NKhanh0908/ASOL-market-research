from __future__ import annotations

import json
from typing import Protocol
from urllib.parse import urlencode, urlparse

from casual_scout.config import Settings
from casual_scout.models import Chart, Entry, HttpResult, ParsedChart
from casual_scout.providers.http import HttpClient


class SupportsGet(Protocol):
    def get(self, url: str) -> HttpResult: ...


def parse_chart(body: bytes, chart: Chart) -> ParsedChart:
    try:
        document = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ParsedChart(chart, [], None, "invalid", ["invalid JSON"])

    feed = document.get("feed") if isinstance(document, dict) else None
    if not isinstance(feed, dict):
        return ParsedChart(chart, [], None, "invalid", ["missing feed"])

    identity_issues = _chart_identity_issues(feed, chart)
    issues = list(identity_issues)
    raw_entries = feed.get("entry")
    if not isinstance(raw_entries, list):
        issues.append("missing feed entries")
        return ParsedChart(chart, [], _label(feed.get("updated")), "invalid", issues)

    if len(raw_entries) > chart.depth:
        issues.append(f"expected {chart.depth} entries, received {len(raw_entries)}")

    entries: list[Entry] = []
    app_ids: set[str] = set()
    for rank, raw_entry in enumerate(raw_entries, start=1):
        entry, entry_issue = _parse_entry(raw_entry, chart.country, rank)
        if entry_issue is not None:
            issues.append(entry_issue)
            continue
        assert entry is not None
        if entry.app_id in app_ids:
            issues.append(f"duplicate app id: {entry.app_id}")
            continue
        app_ids.add(entry.app_id)
        entries.append(entry)

    if identity_issues or any(issue.startswith("duplicate app id") for issue in issues) or len(
        raw_entries
    ) > chart.depth:
        quality = "invalid"
    elif len(entries) < chart.depth:
        quality = "partial"
    else:
        quality = "complete"

    return ParsedChart(
        chart=chart,
        entries=entries,
        source_updated=_label(feed.get("updated")),
        quality=quality,
        issues=issues,
    )


def parse_lookup(body: bytes, requested_ids: list[str]) -> dict[str, dict]:
    try:
        document = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    results = document.get("results") if isinstance(document, dict) else None
    if not isinstance(results, list):
        return {}

    requested = set(requested_ids)
    metadata: dict[str, dict] = {}
    for result in results:
        if not isinstance(result, dict) or "trackId" not in result:
            continue
        app_id = str(result["trackId"])
        if app_id in requested:
            metadata[app_id] = result
    return metadata


class AppleProvider:
    def __init__(self, settings: Settings, http: SupportsGet | None = None) -> None:
        self._settings = settings
        self._http = http or HttpClient(settings)

    def fetch_chart(self, chart: Chart) -> tuple[HttpResult, ParsedChart]:
        url = _chart_url(chart)
        result = self._http.get(url)
        parsed = parse_chart(result.body or b"", chart)
        return result, parsed

    def fetch_metadata(self, country: str, ids: list[str]) -> tuple[HttpResult, dict[str, dict]]:
        if len(ids) > 20:
            raise ValueError("Apple Lookup accepts at most 20 IDs per request")
        country = _country(country)
        query = urlencode({"country": country, "id": ",".join(ids)})
        url = f"https://itunes.apple.com/lookup?{query}"
        result = self._http.get(url)
        return result, parse_lookup(result.body or b"", ids)


def _chart_url(chart: Chart) -> str:
    if not _is_supported_chart(chart):
        raise ValueError("unsupported Apple chart configuration")
    country = _country(chart.country)
    return (
        f"https://itunes.apple.com/{country}/rss/topfreeapplications/limit=100/genre=7003/json"
    )


def _country(value: str) -> str:
    country = value.lower()
    if len(country) != 2 or not country.isalpha():
        raise ValueError("country must be a two-letter code")
    return country


def _chart_identity_issues(feed: dict, chart: Chart) -> list[str]:
    issues: list[str] = []
    if not _is_supported_chart(chart):
        issues.append("unsupported Apple chart configuration")
    title = _label(feed.get("title"))
    if title != "iTunes Store: Top Free Applications in Casual":
        issues.append("title does not identify the Casual chart")

    self_url = None
    links = feed.get("link")
    if isinstance(links, list):
        for link in links:
            attributes = link.get("attributes") if isinstance(link, dict) else None
            if isinstance(attributes, dict) and attributes.get("rel") == "self":
                self_url = attributes.get("href")
                break
    if not isinstance(self_url, str):
        return [*issues, "missing self link"]

    parsed = urlparse(self_url)
    expected_path = (
        f"/{_country(chart.country)}/rss/{chart.collection}/limit={chart.depth}/genre={chart.genre}/json"
    )
    if parsed.scheme != "https" or parsed.hostname != "itunes.apple.com":
        issues.append("self link is not the Apple RSS endpoint")
    elif parsed.path != expected_path:
        path_parts = parsed.path.split("/")
        if len(path_parts) > 1 and path_parts[1] != _country(chart.country):
            issues.append("self link country does not match chart")
        elif f"genre={chart.genre}" not in parsed.path:
            issues.append("self link genre does not match chart")
        else:
            issues.append("self link does not match chart")
    return issues


def _is_supported_chart(chart: Chart) -> bool:
    return (
        chart.provider == "apple"
        and chart.platform == "ios"
        and chart.collection == "topfreeapplications"
        and chart.genre == "7003"
        and chart.depth == 100
        and chart.version == 1
    )


def _parse_entry(raw_entry: object, country: str, rank: int) -> tuple[Entry | None, str | None]:
    if not isinstance(raw_entry, dict):
        return None, f"entry at rank {rank} is not an object"
    app_id = _nested_value(raw_entry, "id", "attributes", "im:id")
    name = _label(raw_entry.get("im:name"))
    store_url = _store_url(raw_entry, country)
    if not isinstance(app_id, str) or not app_id:
        return None, f"entry at rank {rank} is missing app id"
    if not isinstance(name, str) or not name:
        return None, f"entry at rank {rank} is missing name"
    if store_url is None:
        return None, f"entry at rank {rank} has invalid store URL"

    images = raw_entry.get("im:image")
    icon_url = None
    if isinstance(images, list):
        for image in reversed(images):
            icon_url = _label(image)
            if icon_url:
                break
    developer = _label(raw_entry.get("im:artist"))
    category = raw_entry.get("category")
    category_attributes = category.get("attributes") if isinstance(category, dict) else None
    source_genres = [category_attributes] if isinstance(category_attributes, dict) else []
    return Entry(app_id, rank, name, store_url, icon_url, developer, source_genres), None


def _store_url(raw_entry: dict, country: str) -> str | None:
    links = raw_entry.get("link")
    if not isinstance(links, list):
        return None
    for link in links:
        attributes = link.get("attributes") if isinstance(link, dict) else None
        if not isinstance(attributes, dict) or attributes.get("rel") != "alternate":
            continue
        href = attributes.get("href")
        if not isinstance(href, str):
            continue
        parsed = urlparse(href)
        if parsed.scheme == "https" and parsed.hostname == "apps.apple.com":
            path_parts = parsed.path.split("/")
            if len(path_parts) > 1 and path_parts[1] == country:
                return href
    return None


def _nested_value(mapping: dict, *keys: str) -> object:
    value: object = mapping
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _label(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    label = value.get("label")
    return label if isinstance(label, str) else None
