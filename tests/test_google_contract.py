import hashlib
import json
from pathlib import Path


def test_verified_chart_matrix():
    root = Path(__file__).parent / 'fixtures' / 'google_play'
    cases = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    markets = {'vn', 'th', 'id', 'my', 'ph', 'sg', 'la', 'kh', 'us'}
    assert {(x['country'], x['feed']) for x in cases} == {
        (c, f) for c in markets for f in ('top-free', 'top-grossing')
    }
    for case in cases:
        assert case['method'] == 'POST'
        assert case['category'] == 'GAME_CASUAL'
        assert hashlib.sha256((root / case['body_file']).read_bytes()).hexdigest() == case['sha256']
        entries = case['expected_entries']
        count = len(entries)
        if case['feed'] == 'top-free':
            assert count == 100
        else:
            assert 40 <= count <= 100
        assert [x['rank'] for x in entries] == list(range(1, count + 1))
        assert len({x['package'] for x in entries}) == count
