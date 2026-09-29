"""Pure parsing of Google Play category and genre evidence."""
from __future__ import annotations

import re
from urllib.parse import urlparse

_PLAY_GENRE_CODE = re.compile(r"/store/apps/category/(GAME_[A-Z_]+)(?:/|$)")


def extract_store_classification(application_data, genre_items):
    category = application_data.get("applicationCategory")
    if not isinstance(category, str):
        category = None
    genres = []
    seen = set()
    for item in genre_items:
        label = " ".join(str(item.get("label") or "").split())
        href = str(item.get("href") or "")
        match = _PLAY_GENRE_CODE.search(urlparse(href).path)
        code = match.group(1) if match else None
        if not label and not code:
            continue
        key = (label.casefold(), code)
        if key in seen:
            continue
        seen.add(key)
        genres.append({"label": label or code, "code": code})
    return {"application_category": category, "google_play_genres": genres}
