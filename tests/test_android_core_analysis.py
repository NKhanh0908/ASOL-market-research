import pytest
from android_core_support import seed_snapshot

from casual_scout.analysis.monetization import classify_android_monetization
from casual_scout.analysis.service import AnalysisService
from casual_scout.storage import Repository


@pytest.mark.parametrize('price,ads,iap,grossing,expected', [(None,True,False,None,'UNKNOWN'),(0,None,True,None,'UNKNOWN'),(0,True,True,None,'HYBRID'),(0,False,False,10,'PURE_IAP')])
def test_unknown_monetization_stays_unknown(price,ads,iap,grossing,expected):
    assert classify_android_monetization(price=price,has_ads=ads,has_iap=iap,grossing_rank=grossing) == expected


def test_union_and_same_feed_history(tmp_path):
    repo = Repository(tmp_path); repo.initialize()
    a,b = 'com.example.free','com.example.gross'
    seed_snapshot(repo,'pastfree','2026-09-27','top-free',[(a,10),(b,2)])
    seed_snapshot(repo,'pastgross','2026-09-27','top-grossing',[(b,20)])
    seed_snapshot(repo,'free','2026-09-28','top-free',[(a,1)],metadata={a:{'status':'partial'}})
    seed_snapshot(repo,'gross','2026-09-28','top-grossing',[(a,3),(b,5)],metadata={a:{'status':'complete','installs':'5M+','min_installs':5000000},b:{'status':'complete','installs':'1M+','min_installs':1000000,'price':0,'has_ads':False,'has_iap':True}})
    service = AnalysisService(repo)
    service.analyze_date('2026-09-28',['vn'],platform='android')
    rows = {r['app_id']:r for r in repo.get_daily_analytics('2026-09-28','vn',platform='android')}
    assert set(rows) == {a,b}
    assert rows[a]['free_rank'] == 1 and rows[a]['grossing_rank'] == 3
    assert rows[b]['free_rank'] is None and rows[b]['delta_1d'] == 15
    assert rows[b]['delta_3d'] is None and rows[b]['min_installs'] == 1000000
    assert rows[a]['monetization_model'] == 'UNKNOWN'
    assert rows[a]['min_installs'] == 5000000
    service.analyze_date('2026-09-28',['vn'],platform='android')
    assert len(repo.get_daily_analytics('2026-09-28','vn',platform='android')) == 2


def test_grossing_only_market_has_no_free_canonical(tmp_path):
    repo=Repository(tmp_path); repo.initialize()
    seed_snapshot(repo,'gross','2026-09-28','top-grossing',[('com.example.game',1)])
    AnalysisService(repo).analyze_date('2026-09-28',['vn'],platform='android')
    assert repo.get_canonical_snapshot('2026-09-28','vn',platform='android',feed_type='top-free') is None
    assert repo.get_daily_analytics('2026-09-28','vn',platform='android')[0]['free_rank'] is None


def test_partial_source_quality_is_preserved(tmp_path):
    repo=Repository(tmp_path); repo.initialize()
    seed_snapshot(repo,'partial','2026-09-28','top-grossing',[('com.example.game',1)])
    seed_snapshot(repo,'short','2026-09-28','top-grossing',[('com.example.game',1)],quality='partial',hour=13)
    result=AnalysisService(repo).analyze_date('2026-09-28',['vn'],platform='android')
    assert result['chart_quality']['vn']['top-grossing'] == 'partial'
    assert repo.get_snapshot('short')['quality'] == 'partial'


def test_cross_markets_and_historical_metadata_are_platform_scoped(tmp_path):
    repo=Repository(tmp_path); repo.initialize()
    app='com.example.game'
    seed_snapshot(repo,'vn','2026-09-28','top-free',[(app,1)],metadata={app:{'installs':'1M+','min_installs':1000000,'price':0,'has_ads':True,'has_iap':False}})
    seed_snapshot(repo,'us','2026-09-28','top-grossing',[(app,3)],country='us')
    seed_snapshot(repo,'ios','2026-09-28','topfreeapplications',[(app,1)],country='th',platform='ios')
    with repo._connect() as conn:
        before={t:[tuple(r) for r in conn.execute(f'SELECT * FROM {t}')] for t in ('snapshots','entries','snapshot_metadata','metadata_versions','raw_responses')}
    AnalysisService(repo).analyze_date('2026-09-28',['vn','us','th'],platform='android')
    row=repo.get_daily_analytics('2026-09-28','vn',platform='android')[0]
    assert set(row['cross_markets']) == {'vn','us'}
    assert row['min_installs'] == 1000000
    with repo._connect() as conn:
        after={t:[tuple(r) for r in conn.execute(f'SELECT * FROM {t}')] for t in before}
    assert before == after


@pytest.mark.parametrize('feed', ['top-free','top-grossing'])
def test_partial_baseline_absence_cannot_prove_new_entry(tmp_path, feed):
    repo=Repository(tmp_path); repo.initialize()
    observed, absent='com.example.observed','com.example.unobserved'
    seed_snapshot(repo,'baseline','2026-09-27',feed,[(observed,30)],quality='partial')
    seed_snapshot(repo,'today','2026-09-28',feed,[(observed,5),(absent,10)])
    AnalysisService(repo).analyze_date('2026-09-28',['vn'],platform='android')
    rows={r['app_id']:r for r in repo.get_daily_analytics('2026-09-28','vn',platform='android')}
    assert rows[absent]['signal'] == 'STEADY'
    assert rows[absent]['rank_1d_ago'] is None
    assert rows[absent]['delta_1d'] is None
    assert rows[observed]['rank_1d_ago'] == 30
    assert rows[observed]['delta_1d'] == 25
    assert rows[observed]['signal'] == 'FAST_RISER'


def test_complete_baseline_absence_still_proves_new_entry(tmp_path):
    repo=Repository(tmp_path); repo.initialize()
    seed_snapshot(repo,'baseline','2026-09-27','top-free',[('com.example.previous',1)])
    seed_snapshot(repo,'today','2026-09-28','top-free',[('com.example.new',1)])
    AnalysisService(repo).analyze_date('2026-09-28',['vn'],platform='android')
    assert repo.get_daily_analytics('2026-09-28','vn',platform='android')[0]['signal'] == 'NEW_ENTRY'
