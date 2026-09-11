from __future__ import annotations

from typing import Any


def compute_rank_deltas(
    current_entries: dict[str, int],
    past_snapshots: dict[int, dict[str, int]],
) -> dict[str, dict[str, Any]]:
    """Compute rank deltas for 1d, 3d, and 7d ago, and determine new entry status."""
    results: dict[str, dict[str, Any]] = {}
    snap_1d = past_snapshots.get(1)
    snap_3d = past_snapshots.get(3)
    snap_7d = past_snapshots.get(7)

    has_1d_baseline = snap_1d is not None and len(snap_1d) > 0

    for app_id, current_rank in current_entries.items():
        rank_1d: int | None = None
        delta_1d: int | None = None
        is_new_entry = False

        if snap_1d is not None:
            if app_id in snap_1d:
                rank_1d = snap_1d[app_id]
                delta_1d = rank_1d - current_rank
            elif has_1d_baseline:
                is_new_entry = True

        rank_3d: int | None = None
        delta_3d: int | None = None
        if snap_3d is not None and app_id in snap_3d:
            rank_3d = snap_3d[app_id]
            delta_3d = rank_3d - current_rank

        rank_7d: int | None = None
        delta_7d: int | None = None
        if snap_7d is not None and app_id in snap_7d:
            rank_7d = snap_7d[app_id]
            delta_7d = rank_7d - current_rank

        results[app_id] = {
            'rank_1d_ago': rank_1d,
            'delta_1d': delta_1d,
            'rank_3d_ago': rank_3d,
            'delta_3d': delta_3d,
            'rank_7d_ago': rank_7d,
            'delta_7d': delta_7d,
            'is_new_entry': is_new_entry,
        }

    return results


def compute_cross_market_presence(
    country_app_maps: dict[str, list[str] | set[str]],
) -> dict[str, list[str]]:
    """Map each app_id to the list of countries where it appeared in Top 100."""
    presence: dict[str, list[str]] = {}
    for country, app_ids in country_app_maps.items():
        for app_id in app_ids:
            if app_id not in presence:
                presence[app_id] = []
            if country not in presence[app_id]:
                presence[app_id].append(country)

    for countries_list in presence.values():
        countries_list.sort()

    return presence