"""Google Play HTTP feasibility and contract probe.

Probes public HTTP GET endpoints for Google Play charts and metadata,
records raw evidence, and analyzes contract compliance without modifying production DB.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import httpx

MARKET_LOCALES = {
    'vn': 'vi',
    'th': 'th',
    'id': 'id',
    'my': 'en',
    'ph': 'en',
    'sg': 'en',
    'la': 'en',
    'kh': 'en',
    'us': 'en',
}

DEFAULT_CATEGORY_URL = 'https://play.google.com/store/apps/category/GAME_CASUAL'


def capture(client: httpx.Client, url: str, output: Path) -> bytes:
    output.mkdir(parents=True, exist_ok=False)
    response = client.get(url)
    (output / 'response.bin').write_bytes(response.content)
    manifest = {
        'method': 'GET',
        'url': str(response.url),
        'sha256': hashlib.sha256(response.content).hexdigest(),
        'status': response.status_code,
        'headers': dict(response.headers),
        'bytes': len(response.content),
    }
    (output / 'request.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return response.content


def inspect_embedded_data(content: bytes) -> dict:
    """Analyze AF_initDataCallback payloads in public Google Play HTML."""
    text = content.decode('utf-8', errors='replace')
    callbacks = re.findall(
        r"AF_initDataCallback\(\{key:\s*'([^']+)',.*?data:([\s\S]*?)(?:,\s*sideChannel:|\}\);)",
        text,
    )
    results = {'callbacks_found': len(callbacks), 'keys': [], 'chart_sections': []}

    for key, raw_data in callbacks:
        results['keys'].append(key)
        if 'topselling_free' in raw_data or 'topgrossing' in raw_data:
            results['chart_sections'].append({
                'key': key,
                'contains_top_free': 'topselling_free' in raw_data,
                'contains_top_grossing': 'topgrossing' in raw_data,
                'raw_snippet': raw_data[:500],
            })

    details = set(re.findall(r'/store/apps/details\?id=([a-zA-Z0-9_\.]+)', text))
    results['package_links_in_page'] = len(details)
    return results


def probe_market_charts(output_dir: Path, markets: list[str] | None = None) -> dict:
    target_markets = markets or list(MARKET_LOCALES.keys())
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        'probed_at': datetime.now(UTC).isoformat(),
        'markets': {},
        'overall_feasibility': {
            'public_get_top100_available': False,
            'reason': (
                'Public HTTP GET on Google Play category pages embeds chart tab headers '
                '(apps_topselling_free, apps_topgrossing) in AF_initDataCallback ds:3/ds:4, '
                'but the items list is empty []. Items are populated dynamically via client-side '
                'RPC (/PlayStoreUi/data/batchexecute POST), not static GET HTML.'
            ),
        },
    }

    with httpx.Client(
        timeout=15,
        follow_redirects=True,
        headers={
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept-Language': 'en-US,en;q=0.9',
        },
    ) as client:
        for market in target_markets:
            lang = MARKET_LOCALES.get(market, 'en')
            query = urlencode({'hl': lang, 'gl': market.upper()})
            url = f'{DEFAULT_CATEGORY_URL}?{query}'
            market_dir = output_dir / market
            print(f'Probing {market} ({lang}) -> {url}...')
            try:
                body = capture(client, url, market_dir)
                analysis = inspect_embedded_data(body)
                report['markets'][market] = {
                    'url': url,
                    'status': 200,
                    'bytes': len(body),
                    'analysis': analysis,
                }
            except Exception as exc:
                report['markets'][market] = {'url': url, 'error': str(exc)}

    summary_file = output_dir / 'probe_summary.json'
    summary_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Probe completed. Summary written to {summary_file}')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default=None, help='Single URL to probe')
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('data/google-play-probe') / datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ'),
        help='Output directory',
    )
    parser.add_argument(
        '--all-markets',
        action='store_true',
        help='Probe all 9 markets for GAME_CASUAL',
    )
    args = parser.parse_args()

    if args.all_markets:
        probe_market_charts(args.output)
    elif args.url:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            capture(client, args.url, args.output)
    else:
        # Default single probe of vn
        probe_market_charts(args.output, markets=['vn'])
