from __future__ import annotations

from datetime import date as Date, timedelta
from typing import Any
from casual_scout.market_brief.reader import SnapshotData
from casual_scout.mcp.contracts import (
    BriefGameEntry,
    PlatformBrief,
    RankHistoryPoint,
    StrongMove,
)

def compute_game_history(
    app_id: str, target_date: str, snapshots: dict[str, SnapshotData]
) -> list[RankHistoryPoint]:
    end_date = Date.fromisoformat(target_date)
    date_strings = [(end_date - timedelta(days=i)).isoformat() for i in range(7)]
    history: list[RankHistoryPoint] = []

    for d_str in reversed(date_strings):
        snap = snapshots.get(d_str)
        if not snap:
            history.append(RankHistoryPoint(date=d_str, rank=None, status="no_complete_snapshot"))
            continue
        matched = next((e for e in snap.entries if e["app_id"] == app_id), None)
        if matched:
            history.append(RankHistoryPoint(date=d_str, rank=matched["rank"], status="observed"))
        else:
            history.append(RankHistoryPoint(date=d_str, rank=None, status="not_in_observed_chart"))
    return history

def compute_platform_brief(
    country: str, platform: str, target_date: str, snapshots: dict[str, SnapshotData]
) -> PlatformBrief:
    target_snap = snapshots.get(target_date)
    if not target_snap:
        return PlatformBrief(
            data_status="unavailable",
            comparison_status="unavailable",
            warnings=[{"code": "MISSING_TARGET_DATE", "message": f"No complete snapshot for {target_date}"}],
        )

    t_minus_1_str = (Date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
    t_minus_3_str = (Date.fromisoformat(target_date) - timedelta(days=3)).isoformat()
    snap_t1 = snapshots.get(t_minus_1_str)
    snap_t3 = snapshots.get(t_minus_3_str)

    rank_t1_map = {e["app_id"]: e["rank"] for e in snap_t1.entries} if snap_t1 else {}
    rank_t3_map = {e["app_id"]: e["rank"] for e in snap_t3.entries} if snap_t3 else {}

    top_10_list: list[BriefGameEntry] = []
    movers_candidates: list[tuple[float, BriefGameEntry]] = []

    for entry in target_snap.entries:
        app_id = entry["app_id"]
        cur_rank = entry["rank"]
        r1 = rank_t1_map.get(app_id)
        r3 = rank_t3_map.get(app_id)

        delta_1d = (r1 - cur_rank) if r1 is not None else None
        delta_3d = (r3 - cur_rank) if r3 is not None else None

        # Movement 1d
        if r1 is None:
            movement_1d = "new_entry" if snap_t1 is not None else "unknown"
        elif delta_1d > 0:
            movement_1d = "up"
        elif delta_1d < 0:
            movement_1d = "down"
        else:
            movement_1d = "unchanged"

        comp_1d = "available" if r1 is not None else ("no_baseline" if snap_t1 else "unavailable")
        comp_3d = "available" if r3 is not None else ("no_baseline" if snap_t3 else "unavailable")

        strong_moves: list[StrongMove] = []
        ratio_1d = 0.0
        ratio_3d = 0.0

        if delta_1d is not None and abs(delta_1d) >= 20:
            strong_moves.append(
                StrongMove(
                    window_days=1,
                    delta=delta_1d,
                    direction="up" if delta_1d > 0 else "down",
                    threshold=20,
                )
            )
            ratio_1d = abs(delta_1d) / 20.0

        if delta_3d is not None and abs(delta_3d) >= 30:
            strong_moves.append(
                StrongMove(
                    window_days=3,
                    delta=delta_3d,
                    direction="up" if delta_3d > 0 else "down",
                    threshold=30,
                )
            )
            ratio_3d = abs(delta_3d) / 30.0

        history = compute_game_history(app_id, target_date, snapshots)

        brief_entry = BriefGameEntry(
            app_id=app_id,
            name=entry["name"],
            store_url=entry.get("store_url"),
            rank=cur_rank,
            rank_1d_ago=r1,
            rank_3d_ago=r3,
            delta_1d=delta_1d,
            delta_3d=delta_3d,
            movement_1d=movement_1d,
            comparison_1d=comp_1d,
            comparison_3d=comp_3d,
            strong_moves=strong_moves,
            rank_history=history,
        )

        if cur_rank <= 10:
            top_10_list.append(brief_entry)
        elif strong_moves:
            max_ratio = max(ratio_1d, ratio_3d)
            movers_candidates.append((max_ratio, brief_entry))

    # Sort top 10 by current rank
    top_10_list.sort(key=lambda g: g.rank)

    # Sort movers by max ratio descending, then current rank ascending, then app_id
    movers_candidates.sort(key=lambda item: (-item[0], item[1].rank, item[1].app_id))
    movers_list = [item[1] for item in movers_candidates]

    snapshots_summary = {
        d: {
            "snapshot_id": s.snapshot_id,
            "observed_at": s.observed_at,
            "quality": s.quality,
            "raw_hash": s.raw_hash,
        }
        for d, s in snapshots.items()
    }

    comp_status = "available" if snap_t1 and snap_t3 else ("partial" if snap_t1 or snap_t3 else "unavailable")

    return PlatformBrief(
        data_status="available",
        comparison_status=comp_status,
        snapshots=snapshots_summary,
        top_10=top_10_list,
        strong_movers_outside_top_10=movers_list,
        total_top_10=len(top_10_list),
        total_strong_movers=len(movers_list),
    )
