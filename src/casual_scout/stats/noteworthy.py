"""Evidence-led discovery. Dates follow the existing iOS UTC analysis days."""

from collections import defaultdict
from contextlib import closing
from datetime import date, timedelta

from casual_scout.storage import Repository


def observed_charts(repo: Repository, day: str, collection="topfreeapplications") -> dict:
    """One complete chart per market; prefer the pinned canonical if applicable."""
    with closing(repo._connect()) as db:
        rows = db.execute(
            """SELECT s.id, c.country FROM snapshots s
            JOIN market_runs mr ON mr.id=s.market_run_id
            JOIN charts c ON c.id=mr.chart_id
            LEFT JOIN daily_canonical_snapshots d ON d.snapshot_id=s.id AND d.date=?
            WHERE substr(s.observed_at,1,10)=? AND s.quality='complete'
              AND c.collection=? AND c.provider='apple' AND c.platform='ios'
              AND c.genre='7003' AND c.depth=100
            ORDER BY (d.snapshot_id IS NOT NULL) DESC, s.observed_at DESC, s.id DESC""",
            (day, day, collection),
        ).fetchall()
        charts = {}
        for row in rows:
            if row["country"] not in charts:
                entries = db.execute(
                    "SELECT app_id, rank FROM entries WHERE snapshot_id=?", (row["id"],)
                ).fetchall()
                charts[row["country"]] = {str(e["app_id"]): e["rank"] for e in entries}
    return charts


def presence(app_id: str, charts: dict) -> dict:
    markets = sorted(c for c, ranks in charts.items() if str(app_id) in ranks)
    return {
        "presence_markets": markets,
        "presence_count": len(markets) if charts else None,
        "observed_market_count": len(charts),
        "observed_markets": sorted(charts),
    }


def rank_noteworthy(records, current, previous, three_days_ago, shortlisted_app_ids=None):
    """Group real observations by game, then sort by explicit signals, never a score."""
    grouped = defaultdict(list)
    for record in records:
        grouped[str(record["app_id"])].append(record)
    comparable = sorted(current.keys() & previous.keys())
    result = []
    for app_id, variants in grouped.items():
        entry = dict(min(variants, key=lambda r: (r["current_rank"], r["country"])))
        # Cross-market evidence remains global even when the list is filtered to one country.
        markets = sorted(c for c in current if app_id in current[c])
        rising, new, reasons = [], [], []
        has_baseline = False
        for market in markets:
            rank = current[market][app_id]
            old = previous.get(market, {}).get(app_id)
            old3 = three_days_ago.get(market, {}).get(app_id)
            d1 = old - rank if old is not None else None
            d3 = old3 - rank if old3 is not None else None
            has_baseline |= market in previous or old3 is not None
            if market in previous and old is None:
                new.append(market)
                reasons.append(f"{market.upper()}: mới vào BXH tại #{rank}")
            if d1 is not None and d1 >= 20:
                rising.append(market)
                reasons.append(f"{market.upper()}: +{d1} hạng / 1 ngày")
            elif d3 is not None and d3 >= 30:
                rising.append(market)
                reasons.append(f"{market.upper()}: +{d3} hạng / 3 ngày")
        added = [c for c in comparable if app_id in current[c] and app_id not in previous[c]]
        lost = [c for c in comparable if app_id not in current[c] and app_id in previous[c]]
        had_presence = any(app_id in previous[c] for c in comparable)
        expanded = added if had_presence else []
        if expanded:
            reasons.append("Xuất hiện thêm tại " + ", ".join(c.upper() for c in expanded))
        if lost:
            reasons.append("Không còn trong BXH tại " + ", ".join(c.upper() for c in lost))
        if len(rising) >= 2:
            label, priority = "Tăng ở nhiều thị trường", 0
        elif rising:
            label, priority = "Đang tăng", 1
        elif new:
            label, priority = "Mới vào BXH", 2
        elif has_baseline:
            label, priority = "Chưa có tín hiệu nổi bật", 3
        else:
            label, priority = "Chưa đủ dữ liệu so sánh", 4
        entry.update(presence(app_id, current))
        # Historical aggregates cannot prove presence or movement in this observation window.
        entry.pop("cross_market_count", None)
        entry.pop("cross_markets", None)
        market = entry["country"]
        rank = current.get(market, {}).get(app_id)
        for offset, baseline in ((1, previous), (3, three_days_ago)):
            old = baseline.get(market, {}).get(app_id)
            entry[f"delta_{offset}d"] = old - rank if old is not None and rank is not None else None
        entry.update(
            signal=("MULTI_MARKET_RISE", "RISING", "NEW_ENTRY", "NO_SIGNAL", "INSUFFICIENT_DATA")[priority],
            signal_reasons=reasons or [label],
            noteworthy_label=label,
            noteworthy_reasons=reasons or [label],
            rising_markets=rising,
            new_entry_markets=new,
            added_markets=expanded,
            lost_markets=lost,
            comparable_markets=comparable,
            comparison_available=has_baseline,
            noteworthy=priority < 3,
            is_shortlisted=app_id in (shortlisted_app_ids or set()),
        )
        result.append((priority, entry))
    result.sort(key=lambda pair: (pair[0], -len(pair[1]["rising_markets"]),
                                 pair[1]["current_rank"], str(pair[1]["app_id"])))
    return [entry for _, entry in result]


def noteworthy_for_date(repo, records, day, shortlisted_app_ids=None, *, markets=None):
    target = date.fromisoformat(day)
    charts = [observed_charts(repo, (target - timedelta(days=n)).isoformat()) for n in (0, 1, 3)]
    if markets is not None:
        charts = [{c: ranks for c, ranks in chart.items() if c in markets} for chart in charts]
    return rank_noteworthy(records, *charts, shortlisted_app_ids)
