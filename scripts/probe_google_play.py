"""Read-only Google Play feasibility probe; saves evidence, never writes production DB."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

CATEGORY_URL = 'https://play.google.com/store/apps/category/GAME_CASUAL?hl=vi&gl=VN'


class PageInventory(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.headings = []
        self.links = []
        self.current_link = None
        self.current_heading = None
        self.sections = []
        self.section = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'section':
            self.section = {'text': '', 'app_links': [], 'top_free_selected': False}
        if self.section is not None and attrs.get('id') == 'ct|apps_topselling_free':
            self.section['top_free_selected'] = attrs.get('aria-pressed') == 'true'
        if tag == 'a':
            self.current_link = {'href': attrs.get('href', ''), 'text': '', 'label': attrs.get('aria-label', '')}
        if tag in ('h1', 'h2', 'h3'):
            self.current_heading = {'tag': tag, 'text': '', 'link_index': len(self.links)}

    def handle_data(self, data):
        if self.section is not None:
            self.section['text'] += data + ' '
        if self.current_link is not None:
            self.current_link['text'] += data
        if self.current_heading is not None:
            self.current_heading['text'] += data

    def handle_endtag(self, tag):
        if tag == 'a' and self.current_link is not None:
            if self.section is not None and '/store/apps/details?' in self.current_link['href']:
                self.section['app_links'].append(dict(self.current_link))
            self.links.append(self.current_link)
            self.current_link = None
        if tag in ('h1', 'h2', 'h3') and self.current_heading is not None:
            self.headings.append(self.current_heading)
            self.current_heading = None
        if tag == 'section' and self.section is not None:
            self.sections.append(self.section)
            self.section = None


def probe(url, output):
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(UTC).isoformat()
    clock = time.monotonic()
    try:
        with httpx.Client(timeout=30, follow_redirects=True, headers={
            'User-Agent': 'CasualScout/1.0 (+local-market-research)',
            'Accept-Language': 'vi-VN,vi;q=0.9',
        }) as client:
            response = client.get(url)
    except httpx.HTTPError as error:
        report = {'url': url, 'started_at': started, 'error': str(error)}
        (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        raise
    (output / 'response.html').write_bytes(response.content)
    page = PageInventory()
    page.feed(response.text)
    apps = []
    seen = set()
    for link in page.links:
        parsed = urlparse(urljoin(str(response.url), link['href']))
        package = parse_qs(parsed.query).get('id', [None])[0]
        if parsed.path == '/store/apps/details' and package and package not in seen:
            seen.add(package)
            apps.append({'package': package, 'page_order': len(apps) + 1, **link})
    report = {
        'url': url, 'final_url': str(response.url), 'status': response.status_code,
        'started_at': started, 'elapsed_seconds': round(time.monotonic() - clock, 3),
        'bytes': len(response.content), 'sha256': hashlib.sha256(response.content).hexdigest(),
        'content_type': response.headers.get('content-type'),
        'headings': page.headings, 'unique_app_count': len(apps), 'apps_in_page_order': apps,
        'collection_links': [link for link in page.links if 'collection/' in link['href']],
        'top_free_sections': [section for section in page.sections if section['top_free_selected']],
        'verified_chart_rank_count': 0,
        'warning': 'Page order is NOT verified chart rank. Category recommendations may not be Top Free.',
    }
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('status','elapsed_seconds','bytes','unique_app_count','top_free_sections')}, ensure_ascii=True))
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default=CATEGORY_URL)
    parser.add_argument('--output', type=Path, default=Path('data/google-play-probe') / datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ'))
    args = parser.parse_args()
    probe(args.url, args.output)
