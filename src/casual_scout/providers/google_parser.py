"""Evidence-based parsers for Google Play charts and application metadata."""
from __future__ import annotations

import html
import json
import re
from typing import Any

from casual_scout.models import Chart, Entry, ParsedChart


def minimum_from_ascii_display(text: str) -> int | None:
    """Extract minimum install integer from localized or suffixed install display string."""
    if not text:
        return None
    # e.g. "10,000,000+", "1.000.000+"
    comma_match = re.fullmatch(r"([0-9]+(?:[,\.][0-9]{3})*)\+", text.strip())
    if comma_match:
        digits = re.sub(r"[,\.]", "", comma_match.group(1))
        return int(digits)

    # e.g. "50M+", "500K+", "1B+"
    suffix_match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([KMB])\+", text.strip(), re.IGNORECASE)
    if suffix_match:
        val = float(suffix_match.group(1))
        multiplier = {
            "k": 1_000,
            "m": 1_000_000,
            "b": 1_000_000_000,
        }[suffix_match.group(2).lower()]
        return int(val * multiplier)

    return None


def parse_google_chart(body: bytes, chart: Chart) -> ParsedChart:
    """Parse Google Play batchexecute response bytes into a ParsedChart."""
    text = body.decode("utf-8", errors="replace")
    entries: list[Entry] = []
    issues: list[str] = []

    try:
        found_payload = False
        for line in text.strip().split("\n"):
            line = line.strip()
            if line.startswith(")]}'"):
                continue
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            if not isinstance(data, list):
                continue

            for item in data:
                if (
                    isinstance(item, list)
                    and len(item) > 2
                    and item[0] == "wrb.fr"
                    and item[1] == "vyAe2"
                ):
                    found_payload = True
                    inner = json.loads(item[2])
                    apps_container = inner[0][1][0][28][0]
                    seen: set[str] = set()
                    for idx, app_item in enumerate(apps_container):
                        if not isinstance(app_item, list) or not app_item:
                            continue
                        app_info = (
                            app_item[0]
                            if isinstance(app_item[0], list) and app_item[0]
                            else app_item
                        )
                        if not isinstance(app_info, list) or not app_info:
                            continue

                        package = None
                        if isinstance(app_info[0], list) and app_info[0] and isinstance(app_info[0][0], str):
                            package = app_info[0][0]
                        elif isinstance(app_info[0], str):
                            package = app_info[0]
                        elif (
                            len(app_info) > 1
                            and isinstance(app_info[1], list)
                            and app_info[1]
                            and isinstance(app_info[1][0], str)
                        ):
                            package = app_info[1][0]

                        if not package:
                            continue
                        if package in seen:
                            continue
                        seen.add(package)

                        name = app_info[3] if len(app_info) > 3 and isinstance(app_info[3], str) else package
                        developer = app_info[14] if len(app_info) > 14 and isinstance(app_info[14], str) else None
                        icon_url = (
                            app_info[1][3][2]
                            if len(app_info) > 1
                            and isinstance(app_info[1], list)
                            and len(app_info[1]) > 3
                            and isinstance(app_info[1][3], list)
                            and len(app_info[1][3]) > 2
                            else None
                        )
                        store_url = f"https://play.google.com/store/apps/details?id={package}"
                        entries.append(
                            Entry(
                                app_id=package,
                                rank=len(seen),
                                name=name or package,
                                store_url=store_url,
                                icon_url=icon_url,
                                developer=developer,
                                source_genres=[{"name": "Casual"}],
                            )
                        )

        if not found_payload or not entries:
            issues.append("missing vyAe2 batchexecute payload or empty apps list")
            return ParsedChart(chart=chart, entries=[], source_updated=None, quality="invalid", issues=issues)

        # Quality assessment
        if chart.feed_type == "top-free":
            quality = "complete" if len(entries) == 100 else "partial"
        else:
            quality = "complete" if len(entries) >= 40 else "partial"

        return ParsedChart(
            chart=chart,
            entries=entries,
            source_updated=None,
            quality=quality,
            issues=issues,
        )

    except Exception as exc:
        issues.append(f"exception parsing Google Play chart: {exc}")
        return ParsedChart(chart=chart, entries=[], source_updated=None, quality="invalid", issues=issues)


def _safe_get(data: Any, path: list[int]) -> Any:
    current = data
    for idx in path:
        if isinstance(current, (list, tuple)) and 0 <= idx < len(current):
            current = current[idx]
        else:
            return None
    return current


def parse_google_metadata(body: bytes, package: str) -> dict:
    """Parse Google Play app detail page bytes into structured metadata."""
    text = body.decode("utf-8", errors="replace")
    callbacks = dict(
        re.findall(
            r"AF_initDataCallback\(\{key:\s*'([^']+)',.*?data:([\s\S]*?)(?:,\s*sideChannel:|\}\);)",
            text,
        )
    )

    ds5_container = None
    for k, raw_v in callbacks.items():
        try:
            parsed_v = json.loads(raw_v.strip())
            # Search for the container having app details
            candidate = _safe_get(parsed_v, [1, 2])
            if isinstance(candidate, list) and len(candidate) > 13 and isinstance(candidate[13], list):
                ds5_container = candidate
                break
        except Exception:
            pass

    if not ds5_container:
        return {
            "package": package,
            "status": "partial",
            "error": "metadata payload missing ds:5 callback",
            "name": None,
            "developer": None,
            "description": None,
            "genres": [],
            "average_rating": None,
            "rating_count": None,
            "price": None,
            "currency": None,
            "store_url": f"https://play.google.com/store/apps/details?id={package}",
            "icon_url": None,
            "installs": None,
            "min_installs": None,
            "has_ads": None,
            "has_iap": None,
        }

    # Extract name
    name = _safe_get(ds5_container, [0, 0])

    # Extract developer
    developer = _safe_get(ds5_container, [68, 0])

    # Extract description
    raw_desc = (
        _safe_get(ds5_container, [12, 0, 0, 1])
        or _safe_get(ds5_container, [12, 0, 0, 0])
        or _safe_get(ds5_container, [12, 0, 1])
        or _safe_get(ds5_container, [72, 0, 1])
    )
    description = html.unescape(raw_desc) if isinstance(raw_desc, str) else None

    # Extract ratings
    rating_val = _safe_get(ds5_container, [51, 0, 1]) or _safe_get(ds5_container, [51, 1])
    average_rating = float(rating_val) if rating_val is not None else None
    count_val = _safe_get(ds5_container, [51, 2, 1]) or _safe_get(ds5_container, [51, 3])
    rating_count = int(count_val) if count_val is not None else None

    # Extract installs
    installs_list = _safe_get(ds5_container, [13])
    installs_text = None
    min_installs = None
    if isinstance(installs_list, list) and len(installs_list) > 0:
        installs_text = installs_list[0]
        if len(installs_list) > 1 and isinstance(installs_list[1], (int, float)):
            min_installs = int(installs_list[1])
        elif isinstance(installs_text, str):
            min_installs = minimum_from_ascii_display(installs_text)

    # Extract price & currency
    price_val = _safe_get(ds5_container, [57, 0, 0, 0, 0, 1, 0, 0])
    currency = _safe_get(ds5_container, [57, 0, 0, 0, 0, 1, 0, 1])
    if currency is None:
        raw_57 = _safe_get(ds5_container, [57])
        def _search_currency_and_price(node: Any) -> None:
            nonlocal currency, price_val
            if isinstance(node, list):
                for item in node:
                    _search_currency_and_price(item)
            elif isinstance(node, str) and re.fullmatch(r"[A-Z]{3}", node):
                currency = node
            elif isinstance(node, (int, float)) and price_val is None:
                price_val = node
        _search_currency_and_price(raw_57)

    price = (price_val / 1_000_000) if isinstance(price_val, (int, float)) and price_val > 1000 else float(price_val or 0.0)

    # Extract icon
    icon_url = _safe_get(ds5_container, [95, 0, 3, 2]) or _safe_get(ds5_container, [95, 0, 3])
    if not icon_url:
        raw_95 = _safe_get(ds5_container, [95])
        def _search_icon(node: Any) -> None:
            nonlocal icon_url
            if isinstance(node, list):
                for item in node:
                    _search_icon(item)
            elif isinstance(node, str) and node.startswith("http"):
                icon_url = node
        _search_icon(raw_95)

    # Extract flags
    has_ads = bool(_safe_get(ds5_container, [48]))
    has_iap = bool(_safe_get(ds5_container, [19, 0]))

    # Extract genres / categories
    genres: list[dict[str, str]] = []
    genre_name = _safe_get(ds5_container, [79, 0, 0, 0]) or "Casual"
    genres.append({"name": genre_name})

    status = "complete" if name and (min_installs is not None) else "partial"

    return {
        "package": package,
        "status": status,
        "error": None if status == "complete" else "missing core metadata fields",
        "name": name,
        "developer": developer,
        "description": description,
        "genres": genres,
        "average_rating": average_rating,
        "rating_count": rating_count,
        "price": price,
        "currency": currency,
        "store_url": f"https://play.google.com/store/apps/details?id={package}",
        "icon_url": icon_url,
        "installs": installs_text,
        "min_installs": min_installs,
        "has_ads": has_ads,
        "has_iap": has_iap,
    }
