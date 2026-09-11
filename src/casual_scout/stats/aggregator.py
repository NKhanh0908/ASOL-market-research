from collections import Counter, defaultdict
from typing import Any

def compute_genre_distribution(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    if total == 0:
        return {"total": 0, "breakdown": {}}
    
    counts = Counter(r.get("subgenre") or "Unknown" for r in records)
    breakdown = {}
    for genre, count in counts.most_common():
        breakdown[genre] = {
            "count": count,
            "percentage": round((count / total) * 100, 1)
        }
    return {"total": total, "breakdown": breakdown}

def compute_mechanic_distribution(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    if total == 0:
        return {"total": 0, "breakdown": {}}
    
    counts = Counter(r.get("mechanic") or "General" for r in records)
    breakdown = {}
    for mech, count in counts.most_common():
        breakdown[mech] = {
            "count": count,
            "percentage": round((count / total) * 100, 1)
        }
    return {"total": total, "breakdown": breakdown}

def build_market_heatmap(records_by_country: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    countries = sorted(records_by_country.keys())
    all_genres_set = set()
    for recs in records_by_country.values():
        for r in recs:
            all_genres_set.add(r.get("subgenre") or "Unknown")
    
    genres = sorted(list(all_genres_set))
    if not genres:
        return {"countries": countries, "genres": [], "matrix": []}

    matrix = []
    for c in countries:
        c_recs = records_by_country.get(c, [])
        c_counts = Counter(r.get("subgenre") or "Unknown" for r in c_recs)
        row = [c_counts.get(g, 0) for g in genres]
        matrix.append(row)

    return {
        "countries": countries,
        "genres": genres,
        "matrix": matrix
    }

def compute_7day_subgenre_trends(history_records: list[dict[str, Any]]) -> dict[str, Any]:
    if not history_records:
        return {"dates": [], "series": {}}
    
    dates_set = sorted(list(set(r["date"] for r in history_records)))
    genre_date_counts = defaultdict(lambda: Counter())
    
    top_genres_counter = Counter()
    for r in history_records:
        g = r.get("subgenre") or "Unknown"
        d = r["date"]
        genre_date_counts[g][d] += 1
        top_genres_counter[g] += 1
    
    top_5_genres = [g for g, _ in top_genres_counter.most_common(5)]
    
    series = {}
    for g in top_5_genres:
        series[g] = [genre_date_counts[g].get(d, 0) for d in dates_set]

    return {
        "dates": dates_set,
        "series": series
    }
