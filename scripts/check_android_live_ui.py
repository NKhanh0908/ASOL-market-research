"""Read-only browser acceptance check for a running local Android page."""
import json
import os
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data' / 'android-ui-check'
OUTPUT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('SE_CACHE_PATH', str(ROOT / 'data' / 'selenium-cache'))
options = webdriver.ChromeOptions()
options.add_argument('--headless=new')
options.add_argument('--window-size=1440,1100')
options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
driver = webdriver.Chrome(options=options)
report = {}
try:
    driver.get('http://127.0.0.1:8002/android')
    WebDriverWait(driver, 20).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, '.android-game')) > 0)
    report['desktop_cards'] = len(driver.find_elements(By.CSS_SELECTOR, '.android-game'))
    report['progress'] = driver.find_element(By.ID, 'android-count').text
    report['status'] = driver.find_element(By.ID, 'android-status').text
    if 'Đang thu thập' in report['status']:
        initial = report['progress']
        WebDriverWait(driver, 50).until(lambda d:d.find_element(By.ID,'android-count').text != initial)
        report['progress_without_reload'] = driver.find_element(By.ID,'android-count').text
    driver.save_screenshot(str(OUTPUT / 'desktop.png'))
    driver.find_element(By.CSS_SELECTOR, '[data-feed="top-grossing"]').click()
    WebDriverWait(driver, 10).until(lambda d: 'Coin Master' in d.find_element(By.CSS_SELECTOR, '.android-game h2').text)
    report['grossing_first'] = driver.find_element(By.CSS_SELECTOR, '.android-game h2').text
    driver.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {
        'width':390, 'height':844, 'deviceScaleFactor':1, 'mobile':True,
    })
    report['mobile_widths'] = driver.execute_script('return {page:document.documentElement.scrollWidth,viewport:innerWidth}')
    assert report['mobile_widths']['page'] <= report['mobile_widths']['viewport'], report
    driver.save_screenshot(str(OUTPUT / 'mobile.png'))
    report['browser_errors'] = [r for r in driver.get_log('browser') if r['level']=='SEVERE' and 'favicon.ico' not in r['message']]
    assert not report['browser_errors'], report['browser_errors']
    assert driver.find_element(By.ID, 'android-error').get_attribute('hidden') is not None
    print(json.dumps(report, ensure_ascii=True))
finally:
    (OUTPUT/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    driver.quit()
