import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from android_core_support import seed_snapshot

from casual_scout.models import HttpResult
from casual_scout.storage import Repository


@pytest.fixture
def repo(tmp_path):
    value = Repository(tmp_path); value.initialize(); return value


@pytest.mark.parametrize('minimum', [True, -1, 1.5, '100'])
def test_invalid_installs_rejected(repo, minimum):
    result = HttpResult('fixture', datetime.now(UTC), 1, 200, b'{}', {}, None)
    with pytest.raises(ValueError):
        repo.save_metadata('vn', {'com.example.game': {'min_installs': minimum}}, result, provider='google', platform='android')


def test_partial_binding_is_not_complete(repo):
    seed_snapshot(repo, 'partial', '2026-09-28', 'top-free', [('com.example.game', 1)], metadata={'com.example.game': {'status': 'partial'}})
    with repo._connect() as conn:
        assert conn.execute("SELECT enrichment_status FROM market_runs WHERE id='partial'").fetchone()[0] == 'partial'


def test_canonical_rejects_wrong_feed_country_day_and_platform(repo):
    seed_snapshot(repo, 'free', '2026-09-28', 'top-free', [('com.example.game', 1)])
    for day, country, platform, feed in [('2026-09-27','vn','android','top-free'), ('2026-09-28','us','android','top-free'), ('2026-09-28','vn','ios','top-free'), ('2026-09-28','vn','android','top-grossing')]:
        with pytest.raises(ValueError):
            repo.save_canonical_snapshot(day,country,'free','2026-09-28T12:00:00Z',platform=platform,feed_type=feed)


def test_cross_platform_analytics_collision_raises_and_rolls_back(repo):
    base = {'date': '2026-09-28', 'country': 'vn', 'app_id': 'com.example.game', 'current_rank': 1, 'platform': 'android', 'signal_reasons': [], 'cross_markets': ['vn'], 'mechanic': 'Unknown'}
    repo.save_daily_analytics([base])
    with repo._write_connection() as conn:
        conn.execute("UPDATE daily_rank_analytics SET platform='ios'")
    with pytest.raises(ValueError):
        repo.save_daily_analytics([dict(base, app_id='com.example.other'), base])
    assert repo.get_daily_analytics('2026-09-28','vn',platform='android') == []


def test_android_cache_exact_boundary_and_partial_exclusion(repo):
    stamp = datetime(2026,9,28,tzinfo=UTC)
    result = HttpResult('fixture',stamp,1,200,b'{}',{},None)
    kwargs = {'provider': 'google','platform': 'android'}
    versions = repo.save_metadata('vn',{'com.example.game':{'status':'complete','min_installs':0}},result,**kwargs)
    assert repo.cached_metadata('vn',['com.example.game'],stamp+timedelta(hours=48),**kwargs) == versions
    assert repo.cached_metadata('vn',['com.example.game'],stamp+timedelta(hours=48,microseconds=1),**kwargs) == {}
    assert repo.cached_metadata('us',['com.example.game'],stamp,**kwargs) == {}
    assert repo.cached_metadata('vn',['com.example.game'],stamp-timedelta(seconds=1),**kwargs) == {}


def test_history_is_a_calendar_window(repo):
    base = {'country': 'vn','app_id': 'com.example.game','current_rank': 1,'platform': 'android','mechanic': 'Unknown','signal_reasons': [],'cross_markets': ['vn']}
    repo.save_daily_analytics([dict(base,date='2026-09-28'),dict(base,date='2026-08-01')])
    assert [r['date'] for r in repo.get_app_rank_history('com.example.game','vn',platform='android')] == ['2026-09-28']


def test_migration_copies_actual_legacy_feed(repo):
    seed_snapshot(repo,'legacy','2026-09-28','topgrossingapplications',[('123',1)],platform='ios')
    with repo._write_connection() as conn:
        conn.execute("INSERT INTO daily_canonical_snapshots VALUES('2026-09-28','vn','legacy','2026-09-28T12:00:00Z','2026-09-28T12:00:00Z')")
    repo.initialize(); repo.initialize()
    assert repo.get_canonical_snapshot('2026-09-28','vn',feed_type='top-grossing')['snapshot_id'] == 'legacy'
    with repo._connect() as conn:
        assert conn.execute("SELECT feed_type FROM platform_canonical_snapshots WHERE snapshot_id='legacy'").fetchone()[0] == 'top-grossing'
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []


def test_additive_columns_repeatable_preserves_old_rows(tmp_path):
    from casual_scout.storage.migrations_android import migrate_android_columns
    with sqlite3.connect(tmp_path/'old.sqlite3') as conn:
        conn.execute('CREATE TABLE metadata_versions(id TEXT PRIMARY KEY, platform TEXT,country TEXT,fetched_at TEXT)')
        conn.execute("INSERT INTO metadata_versions VALUES('old-meta','ios','vn','2026-09-27T00:00:00Z')")
        conn.execute('CREATE TABLE daily_rank_analytics(id TEXT PRIMARY KEY,date TEXT,country TEXT)')
        conn.execute("INSERT INTO daily_rank_analytics VALUES('old-row','2026-09-27','vn')")
        migrate_android_columns(conn); migrate_android_columns(conn)
        assert conn.execute('SELECT id,installs,min_installs FROM metadata_versions').fetchone() == ('old-meta',None,None)
        assert conn.execute('SELECT id,platform FROM daily_rank_analytics').fetchone() == ('old-row','ios')


@pytest.mark.parametrize('identity', ['123', 'com..game', 'com.123game', '', 'com-game'])
def test_invalid_android_identity_rejected_before_raw_write(repo,identity):
    result=HttpResult('fixture',datetime.now(UTC),1,200,b'{}',{},None)
    with pytest.raises(ValueError):
        repo.save_metadata('vn',{identity:{}},result,provider='google',platform='android')
    with repo._connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM raw_responses').fetchone()[0] == 0


def test_mixed_platform_backup_and_immutable_core(tmp_path):
    from casual_scout.operations.backup import create_backup, restore_backup
    repo=Repository(tmp_path/'source'); repo.initialize()
    seed_snapshot(repo,'android','2026-09-28','top-free',[('com.example.game',1)],metadata={'com.example.game':{'installs':'1M+','min_installs':1000000}})
    seed_snapshot(repo,'ios','2026-09-28','topfreeapplications',[('123',1)],platform='ios',metadata={'123':{'trackName':'iOS'}})
    tables=('snapshots','entries','snapshot_metadata','metadata_versions','raw_responses')
    def fingerprint(value):
        with value._connect() as conn:
            return {t:sorted((tuple(r) for r in conn.execute(f'SELECT * FROM {t}')),key=repr) for t in tables}
    before=fingerprint(repo)
    restored=restore_backup(create_backup(repo,tmp_path/'backup'),tmp_path/'restored')
    assert fingerprint(restored) == before
    with restored._connect() as conn:
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []
        for table in ('snapshots','entries','snapshot_metadata','metadata_versions'):
            for statement in (f'DELETE FROM {table}', f'UPDATE {table} SET '+('snapshot_id=snapshot_id' if table in ('entries','snapshot_metadata') else 'id=id')):
                with pytest.raises(sqlite3.DatabaseError):
                    conn.execute(statement)
    assert fingerprint(restored) == before
