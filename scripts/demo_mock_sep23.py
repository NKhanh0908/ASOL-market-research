"""Build an isolated, read-only web demo. Never modify the source database."""
import json
import shutil
import sqlite3
from pathlib import Path

from casual_scout.analysis.service import AnalysisService
from casual_scout.config import Settings
from casual_scout.storage import Repository
from casual_scout.web.app import create_app
from fastapi.responses import Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data"
DEST = SOURCE / "demo-mock-2026-09-23"
SNAPSHOT = "mock-vn-2026-09-23"
STAMP = "2026-09-23T00:00:00Z"

c
def build():
    DEST.mkdir(exist_ok=False)
    with sqlite3.connect((SOURCE / "casual-scout.sqlite3").as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(DEST / "casual-scout.sqlite3") as db:
            source.backup(db)
    if (SOURCE / "raw").exists():
        shutil.copytree(SOURCE / "raw", DEST / "raw")
    repo = Repository(DEST)
    repo.initialize()
    with repo._write_connection() as db:
        source = db.execute("""SELECT s.* FROM snapshots s JOIN market_runs m ON m.id=s.market_run_id
            JOIN charts c ON c.id=m.chart_id WHERE c.country='vn'
            AND c.collection='topfreeapplications' AND s.quality='complete'
            AND substr(s.observed_at,1,10)='2026-09-22' ORDER BY s.observed_at DESC LIMIT 1""").fetchone()
        if source is None:
            raise RuntimeError("Missing complete VN snapshot for September 22")

        def insert(table, row, **changes):
            values = dict(row)
            values.update(changes)
            columns = ','.join('"' + key + '"' for key in values)
            db.execute(f'INSERT INTO {table} ({columns}) VALUES ({",".join("?" for _ in values)})', tuple(values.values()))

        market = db.execute("SELECT * FROM market_runs WHERE id=?", (source['market_run_id'],)).fetchone()
        run = db.execute("SELECT * FROM runs WHERE id=?", (market['run_id'],)).fetchone()
        insert('runs', run, id=SNAPSHOT, request_key=SNAPSHOT, status='running', started_at=STAMP, ended_at=None,
               summary_json=json.dumps({'is_mock': True, 'source_snapshot_id': source['id'], 'note': 'Synthetic ranks; not historical Apple data'}))
        insert('market_runs', market, id=SNAPSHOT, run_id=SNAPSHOT, started_at=STAMP, ended_at=STAMP)
        insert('snapshots', source, id=SNAPSHOT, market_run_id=SNAPSHOT, observed_at=STAMP,
               source_updated=None, issues_json=json.dumps(['MOCK: ranks rotated within groups of ten from September 22']))
        entries = db.execute('SELECT * FROM entries WHERE snapshot_id=? ORDER BY rank', (source['id'],)).fetchall()
        ordered = []
        for start in range(0, len(entries), 10):
            group = entries[start:start+10]
            ordered.extend(group[3:] + group[:3])
        for rank, entry in enumerate(ordered, 1):
            insert('entries', entry, snapshot_id=SNAPSHOT, rank=rank)
        for row in db.execute('SELECT * FROM snapshot_metadata WHERE snapshot_id=?', (source['id'],)).fetchall():
            insert('snapshot_metadata', row, snapshot_id=SNAPSHOT)
        db.execute("UPDATE runs SET status='succeeded',ended_at=? WHERE id=?", (STAMP,SNAPSHOT))
        db.execute('UPDATE daily_schedule SET enabled=0')
        db.execute("UPDATE one_time_collection_schedule SET status='empty'")
    for day in ('2026-09-22','2026-09-23','2026-09-24'):
        AnalysisService(repo).analyze_date(day, ['vn'])
    (DEST / 'MOCK_DATA.json').write_text(json.dumps({
        'is_mock_demo': True, 'mock_date': '2026-09-23', 'snapshot_id': SNAPSHOT,
        'source_snapshot_id': source['id'],
        'method': 'Rotate each group of 10 ranks by 3 positions; copy metadata from September 22.',
        'warning': 'September 23 and all derived comparisons are synthetic. Original data directory is untouched.'
    }, indent=2), encoding='utf-8')
    print(DEST)


class NoScheduler:
    def start(self):
        pass

    def stop(self):
        pass


def demo_app():
    app = create_app(Settings(DEST), scheduler_factory=lambda *_: NoScheduler())
    for middleware in app.user_middleware:
        if middleware.cls is TrustedHostMiddleware:
            middleware.kwargs['allowed_hosts'].append('192.168.1.4')

    @app.middleware('http')
    async def read_only(request, call_next):
        if request.method not in ('GET', 'HEAD', 'OPTIONS') or request.url.path.startswith(('/export', '/evidence')):
            return Response('MOCK demo is read-only; exports are disabled to avoid mixing synthetic data.', status_code=403)
        return await call_next(request)
    return app


if __name__ == '__main__':
    import sys
    if '--serve' in sys.argv:
        import uvicorn
        uvicorn.run(demo_app(), host='0.0.0.0', port=8001)
    else:
        build()
