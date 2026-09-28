from contextlib import closing
from datetime import UTC, datetime
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from casual_scout.collection.jobs import JobService
from casual_scout.config import Settings
from casual_scout.operations.daily_scheduler import DailyScheduler
from casual_scout.storage import Repository
from casual_scout.web.app import create_app

EXPECTED = {'vn', 'th', 'id', 'my', 'ph', 'sg', 'la', 'kh', 'us'}


def run_markets(repo, run_id):
    with closing(repo._connect()) as db:
        rows = db.execute('''SELECT c.country, c.collection FROM market_runs mr
            JOIN charts c ON c.id=mr.chart_id WHERE mr.run_id=?''', (run_id,)).fetchall()
    assert len(rows) == 9
    assert {r['collection'] for r in rows} == {'topfreeapplications'}
    return {r['country'] for r in rows}


class CrawlForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.inside = attrs.get('action') == '/runs'
        if self.inside and tag == 'input' and 'name' in attrs:
            self.fields[attrs['name']] = attrs.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'form':
            self.inside = False


class MarketOptions(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.values = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'select':
            self.inside = attrs.get('id') in {'country-select', 'country_select'}
        if self.inside and tag == 'option':
            self.values.append(attrs.get('value'))

    def handle_endtag(self, tag):
        if tag == 'select':
            self.inside = False


@pytest.mark.parametrize('page', ['/dashboard', '/data'])
def test_market_filter_matches_group_and_crawl_button_is_explicit(tmp_path, page):
    client = TestClient(create_app(Settings(tmp_path)), base_url='http://127.0.0.1:8000')
    response = client.get(page)
    options = MarketOptions()
    options.feed(response.text)
    assert set(options.values) - {'all'} == EXPECTED
    assert 'Crawl ngay · 9 thị trường' in response.text
    assert 'lần lượt' in response.text


def test_dashboard_all_excludes_outside_group_but_preserves_history(tmp_path):
    from test_analysis_service import _create_snapshot_with_entries

    from casual_scout.web.views import get_dashboard_view, get_data_view

    repo = Repository(tmp_path)
    repo.initialize()
    repo.save_daily_analytics([
        {'id': 'an-' + country, 'date': '2026-09-25', 'country': country, 'app_id': '1001',
         'current_rank': 1, 'signal': 'STEADY', 'signal_reasons': [], 'subgenre': 'Puzzle',
         'mechanic': 'Other', 'mechanic_confidence': 'low', 'cross_market_count': 1,
         'cross_markets': [country], 'created_at': '2026-09-25T00:00:00Z'}
        for country in ('vn', 'bn')
    ])
    for country in ('vn', 'bn'):
        _create_snapshot_with_entries(repo, country, country, country, '2026-09-25',
                                      '2026-09-25T08:00:00Z', [('1001', 1, 'Game')])
    view = get_dashboard_view(repo, date_str='2026-09-25', country='all')
    assert view['summary']['total_games'] == 1
    assert {r['country'] for r in view['radar_items']} == {'vn'}
    assert view['radar_items'][0]['observed_markets'] == ['vn']
    with closing(repo._connect()) as db:
        assert db.execute('SELECT count(*) FROM daily_rank_analytics').fetchone()[0] == 2
    # Old direct links must not silently become Vietnam.
    assert get_data_view(repo, country='bn')['current_market']['country'] == 'bn'


@pytest.mark.parametrize('page', ['/dashboard?country=vn', '/data?country=sg'])
def test_actual_crawl_form_submits_nine_markets(tmp_path, page):
    launched = []
    app = create_app(Settings(tmp_path), launcher=lambda rid, path: launched.append(rid) or 42)
    client = TestClient(app, base_url='http://127.0.0.1:8000')
    form = CrawlForm()
    response = client.get(page)
    form.feed(response.text)
    result = client.post('/runs', data=form.fields,
                         headers={'Origin': 'http://127.0.0.1:8000'}, follow_redirects=False)
    assert result.status_code == 303
    assert len(launched) == 1
    assert run_markets(Repository(tmp_path), launched[0]) == EXPECTED


@pytest.mark.parametrize('kind', ['daily', 'one-time'])
def test_existing_schedules_use_same_nine_markets_after_restart(tmp_path, kind):
    repo = Repository(tmp_path)
    repo.initialize()
    due = datetime(2026, 9, 26, 0, 0, tzinfo=UTC)
    if kind == 'daily':
        repo.set_daily_schedule_enabled(True)
    else:
        repo.schedule_one_time_collection(due, '2026-09-26T07:00')
    repo = Repository(tmp_path)
    repo.initialize()
    launched = []
    scheduler = DailyScheduler(repo, lambda rid, path: launched.append(rid) or 42, now=lambda: due)
    run_id = scheduler.check_once()
    assert run_markets(repo, run_id) == EXPECTED
    assert len(launched) == 1
    assert scheduler.check_once() == ('active_run' if kind == 'daily' else 'disabled')
    JobService(repo).finish(run_id, 'succeeded')
    scheduler.check_once()
    assert len(launched) == 1


def test_schedule_api_reports_effective_group(tmp_path):
    app = create_app(Settings(tmp_path), launcher=lambda *_: 42)
    client = TestClient(app, base_url='http://127.0.0.1:8000')
    assert set(client.get('/api/schedule').json()['countries']) == EXPECTED
    assert set(client.get('/api/one-time-schedule').json()['countries']) == EXPECTED
