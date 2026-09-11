from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Chart:
    country: str
    provider: str = "apple"
    platform: str = "ios"
    collection: str = "topfreeapplications"
    genre: str = "7003"
    depth: int = 100
    version: int = 1
    feed_type: str = "top-free"

    def __post_init__(self):
        if self.feed_type in ("top-grossing", "topgrossingapplications") or self.collection in ("topgrossingapplications", "top-grossing"):
            object.__setattr__(self, "feed_type", "top-grossing")
            object.__setattr__(self, "collection", "topgrossingapplications")
        else:
            object.__setattr__(self, "feed_type", "top-free")
            object.__setattr__(self, "collection", "topfreeapplications")


@dataclass(frozen=True, slots=True)
class Entry:
    app_id: str
    rank: int
    name: str
    store_url: str
    icon_url: str | None
    developer: str | None
    source_genres: list[dict]


@dataclass(frozen=True, slots=True)
class ParsedChart:
    chart: Chart
    entries: list[Entry]
    source_updated: str | None
    quality: str
    issues: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class HttpResult:
    url: str
    started_at: datetime
    elapsed_ms: int
    status: int | None
    body: bytes | None
    headers: dict[str, str]
    error: str | None
    attempts: tuple["HttpResult", ...] = ()
