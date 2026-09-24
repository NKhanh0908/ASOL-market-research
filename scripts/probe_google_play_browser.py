"""Experimental Selenium probe: rendered charts and a bounded metadata sample.

No production database writes. ChromeDriver is auto-resolved unless --driver is set.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

URL = 'https://play.google.com/store/apps/category/GAME_CASUAL?hl=vi&gl=VN'


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def capture(driver, directory, name):
    (directory / f'{name}.html').write_text(driver.page_source, encoding='utf-8')
    driver.save_screenshot(str(directory / f'{name}.png'))


def run(args):
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault('SE_CACHE_PATH', str(Path('data/selenium-cache').resolve()))
    options = webdriver.ChromeOptions()
    if args.headless:
        options.add_argument('--headless=new')
    options.add_argument('--window-size=1440,1100')
    options.add_argument('--lang=vi-VN')
    options.add_argument('--no-first-run')
    options.page_load_strategy = 'eager'
    report = {'started_at': datetime.now(UTC).isoformat(), 'url': URL,
              'charts': {}, 'metadata': [], 'errors': [], 'revenue_amount': None}
    driver = None
    start = time.monotonic()
    try:
        driver = webdriver.Chrome(service=Service(str(args.driver)) if args.driver else Service(), options=options)
        driver.set_page_load_timeout(45)
        report['browser_version'] = driver.capabilities.get('browserVersion')
        report['driver_version'] = driver.capabilities.get('chrome', {}).get('chromedriverVersion')
        for chart, button in [('top-free','ct|apps_topselling_free'), ('top-grossing','ct|apps_topgrossing')]:
            clock = time.monotonic()
            try:
                driver.get(URL)
                control = WebDriverWait(driver, 35).until(lambda d: d.find_element(By.ID, button))
                old_section = control.find_element(By.XPATH, './ancestor::section')
                old_urls = [a.get_attribute('href') for a in old_section.find_elements(By.CSS_SELECTOR, 'a[href*="/store/apps/details?"]')]
                switching = control.get_attribute('aria-pressed') != 'true'
                control.click()
                stable = {'signature': None, 'since': time.monotonic()}
                def loaded(d):
                    selected = d.find_element(By.ID, button)
                    section = selected.find_element(By.XPATH, './ancestor::section')
                    links = section.find_elements(By.CSS_SELECTOR, 'a[href*="/store/apps/details?"]')
                    urls = [a.get_attribute('href') for a in links if a.is_displayed()]
                    if selected.get_attribute('aria-pressed') != 'true' or not urls:
                        return False
                    if switching and urls == old_urls:
                        return False
                    if stable['signature'] != urls:
                        stable.update(signature=urls, since=time.monotonic())
                        return False
                    return section if time.monotonic()-stable['since'] >= 2 else False
                section = WebDriverWait(driver, 40).until(loaded)
                section.screenshot(str(output / f'{chart}-section.png'))
                candidates = driver.execute_script('''
                    return Array.from(arguments[0].querySelectorAll('a[href*="/store/apps/details?"]'))
                      .filter(a=>a.getClientRects().length && getComputedStyle(a).visibility !== 'hidden')
                      .map(a=>({url:a.href,text:a.innerText,aria_label:a.getAttribute('aria-label'),
                        parent_text:a.parentElement.innerText,
                        icon_url:a.querySelector('img')?.src || null}));
                ''', section)
                rows = []
                seen = set()
                for candidate in candidates:
                    package = parse_qs(urlparse(candidate['url']).query).get('id', [None])[0]
                    if package and package not in seen:
                        seen.add(package)
                        lines = candidate['text'].splitlines()
                        visible_rank = int(lines[0]) if lines and lines[0].isdigit() else None
                        rows.append({'package': package, 'rank': visible_rank,
                            'name': lines[1] if visible_rank is not None and len(lines)>1 else None,
                            'section_order': len(rows)+1, **candidate})
                if [row['rank'] for row in rows] != list(range(1,len(rows)+1)):
                    raise ValueError('Visible ranks are missing, duplicated or non-contiguous; refusing chart')
                report['charts'][chart] = {'entries': rows, 'count': len(rows),
                    'section_text': section.text, 'elapsed_seconds': round(time.monotonic()-clock,3),
                    'rank_note': 'Ranks extracted from visible numeric text; contiguous ranks validated. Screenshot saved.'}
                print(json.dumps({'chart':chart,'count':len(rows),'first':rows[:2]},ensure_ascii=True), flush=True)
            except Exception as error:
                report['errors'].append({'stage':chart,'error':str(error)})
                print(f'{chart}: {type(error).__name__}', flush=True)
            finally:
                capture(driver, output, chart)
                save_json(output/'report.json', report)
        entries = report['charts'].get('top-free',{}).get('entries',[])
        for entry in entries[:args.metadata_limit]:
            package = entry['package']
            try:
                time.sleep(2)
                driver.get(f'https://play.google.com/store/apps/details?id={package}&hl=vi&gl=VN')
                WebDriverWait(driver, 30).until(lambda d:d.find_elements(By.TAG_NAME,'h1'))
                structured = []
                for element in driver.find_elements(By.CSS_SELECTOR,'script[type="application/ld+json"]'):
                    try:
                        structured.append(json.loads(element.get_attribute('textContent')))
                    except ValueError:
                        pass
                body = driver.find_element(By.TAG_NAME,'body').text
                report['metadata'].append({'package':package,'json_ld':structured,'visible_text':body,
                    'developer_links':[{'text':a.text,'url':a.get_attribute('href')} for a in driver.find_elements(By.CSS_SELECTOR,'a[href*="/store/apps/dev"]')],
                    'revenue_amount':None})
                capture(driver,output,package)
                print(f'metadata: {package}',flush=True)
            except Exception as error:
                report['errors'].append({'stage':package,'error':str(error)})
            save_json(output/'report.json',report)
    except Exception as error:
        report['errors'].append({'stage':'browser','error':str(error)})
        raise
    finally:
        report['elapsed_seconds'] = round(time.monotonic()-start,3)
        save_json(output/'report.json',report)
        if driver:
            driver.quit()
        print(str(output),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--driver',type=Path)
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--metadata-limit',type=int,default=3,choices=range(0,11))
    parser.add_argument('--output',type=Path,default=Path('data/google-play-browser-probe')/datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ'))
    run(parser.parse_args())
