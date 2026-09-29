"""Synthetic immutable core snapshot fixtures; never live-source evidence."""
import json
from datetime import datetime

from casual_scout.models import HttpResult
from casual_scout.storage.raw import RawStore


def seed_snapshot(repo, sid, day, feed, entries, country="vn", platform="android", metadata=None, quality="complete", hour=12):
    provider = "google" if platform == "android" else "apple"
    stamp = f"{day}T{hour:02d}:00:00Z"
    raw_hash, raw_path = RawStore(repo.data_dir/'raw').put(json.dumps({"snapshot": sid, "entries": entries}).encode())
    with repo._write_connection() as conn:
        conn.execute("INSERT INTO runs(id,request_key,trigger,status,started_at) VALUES(?,?,'manual','running',?)", (sid, sid, stamp))
        conn.execute("INSERT OR IGNORE INTO charts(id,provider,platform,country,collection,genre,depth,version,endpoint,created_at) VALUES(?,?,?,?,?,'GAME_CASUAL',100,1,'fixture',?)", (sid, provider, platform, country, feed, stamp))
        chart_id = conn.execute("SELECT id FROM charts WHERE provider=? AND platform=? AND country=? AND collection=?", (provider, platform, country, feed)).fetchone()[0]
        conn.execute("INSERT INTO market_runs(id,run_id,chart_id,chart_status,enrichment_status,started_at) VALUES(?,?,?,'complete','partial',?)", (sid, sid, chart_id, stamp))
        conn.execute("INSERT INTO raw_responses(hash,path,endpoint,status,received_at,headers_json,size_bytes) VALUES(?,?,'fixture',200,?,'{}',?)", (raw_hash, raw_path.relative_to(repo.data_dir).as_posix(), stamp, raw_path.stat().st_size))
        conn.execute("INSERT INTO snapshots(id,market_run_id,raw_hash,observed_at,quality,issues_json) VALUES(?,?,?,?,?,'[]')", (sid, sid, raw_hash, stamp, quality))
        for aid, rank in entries:
            ref = repo._ensure_app(conn, provider, platform, aid, datetime.fromisoformat(stamp))
            conn.execute("INSERT INTO entries(snapshot_id,app_ref,app_id,rank,name,store_url,source_genres_json) VALUES(?,?,?,?,?,'fixture','[]')", (sid, ref, aid, rank, aid))
    if metadata:
        result = HttpResult('fixture', datetime.fromisoformat(stamp), 1, 200, json.dumps(metadata,sort_keys=True).encode(), {}, None)
        versions = repo.save_metadata(country, metadata, result, provider=provider, platform=platform)
        repo.bind_metadata(sid, versions)
    return sid
