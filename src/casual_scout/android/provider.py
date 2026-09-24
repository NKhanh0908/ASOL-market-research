from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

URL = "https://play.google.com/store/apps/category/GAME_CASUAL?hl=vi&gl=VN"
PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$")
BUTTONS = {"top-free": "ct|apps_topselling_free", "top-grossing": "ct|apps_topgrossing"}
LOG = logging.getLogger(__name__)


class GooglePlayBrowser:
    """One isolated, headless Chrome session per collection; no personal profile."""

    def __init__(self, evidence_dir):
        self.directory = evidence_dir
        self.driver = None

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("SE_CACHE_PATH", str(self.directory.parents[1] / "selenium-cache"))
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1440,1100")
        options.add_argument("--lang=vi-VN")
        options.add_argument("--no-first-run")
        options.page_load_strategy = "eager"
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(40)
        return self

    def __exit__(self, *_):
        if self.driver:
            self.driver.quit()

    def capture(self, name):
        body = self.driver.page_source.encode("utf-8")
        path = self.directory / f"{name}.html"
        path.write_bytes(body)
        self.driver.save_screenshot(str(self.directory / f"{name}.png"))
        manifest = {
            "url": self.driver.current_url,
            "observed_at": datetime.now(UTC).isoformat(),
            "sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body),
            "browser_version": self.driver.capabilities.get("browserVersion"),
        }
        path.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return str(path.relative_to(self.directory.parents[1]))

    def _wait_chart(self, button, old_urls=None):
        state = {"urls": None, "since": time.monotonic()}

        def loaded(driver):
            control = driver.find_element(By.ID, button)
            section = control.find_element(By.XPATH, "./ancestor::section")
            urls = [
                a.get_attribute("href")
                for a in section.find_elements(By.CSS_SELECTOR, 'a[href*="/store/apps/details?"]')
                if a.is_displayed()
            ]
            if control.get_attribute("aria-pressed") != "true" or not urls:
                return False
            if old_urls is not None and old_urls == urls:
                return False
            if state["urls"] != urls:
                state.update(urls=urls, since=time.monotonic())
                return False
            return section if time.monotonic() - state["since"] >= 2 else False

        return WebDriverWait(self.driver, 35).until(loaded)

    def chart(self, feed):
        try:
            self.driver.get(URL)
            WebDriverWait(self.driver, 30).until(
                lambda d: d.find_elements(By.ID, BUTTONS["top-free"])
            )
            free = self._wait_chart(BUTTONS["top-free"])
            if feed == "top-free":
                section = free
            else:
                before = [
                    a.get_attribute("href")
                    for a in free.find_elements(By.CSS_SELECTOR, 'a[href*="/store/apps/details?"]')
                    if a.is_displayed()
                ]
                self.driver.find_element(By.ID, BUTTONS[feed]).click()
                section = self._wait_chart(BUTTONS[feed], before)
            candidates = self.driver.execute_script(
                """
                return Array.from(arguments[0].querySelectorAll('a[href*="/store/apps/details?"]'))
                  .filter(a=>a.getClientRects().length && getComputedStyle(a).visibility !== 'hidden')
                  .map(a=>({url:a.href,text:a.innerText,icon_url:a.querySelector('img')?.src||null}));
            """,
                section,
            )
            rows = []
            seen = set()
            for candidate in candidates:
                package = parse_qs(urlparse(candidate["url"]).query).get("id", [""])[0]
                lines = candidate["text"].splitlines()
                if not PACKAGE.fullmatch(package) or len(lines) < 2 or not lines[0].isdigit():
                    raise ValueError("Invalid package or visible chart rank")
                if package in seen:
                    continue
                seen.add(package)
                rows.append(
                    {
                        "package": package,
                        "rank": int(lines[0]),
                        "name": lines[1],
                        "url": candidate["url"],
                        "icon_url": candidate["icon_url"],
                    }
                )
            if not rows or [r["rank"] for r in rows] != list(range(1, len(rows) + 1)):
                raise ValueError("Missing or non-contiguous chart ranks")
            return rows, self.capture(feed)
        except Exception:
            try:
                self.capture(f"{feed}-error")
            except Exception:
                LOG.exception("Could not capture chart failure evidence")
            raise

    def metadata(self, package):
        if not PACKAGE.fullmatch(package):
            raise ValueError("invalid package")
        time.sleep(1)
        try:
            self.driver.get(f"https://play.google.com/store/apps/details?id={package}&hl=vi&gl=VN")

            def software(driver):
                for element in driver.find_elements(
                    By.CSS_SELECTOR, 'script[type="application/ld+json"]'
                ):
                    try:
                        value = json.loads(element.get_attribute("textContent"))
                    except ValueError:
                        continue
                    if isinstance(value, dict) and value.get("@type") == "SoftwareApplication":
                        return value
                return False

            data = WebDriverWait(self.driver, 25).until(software)
            page_package = parse_qs(urlparse(data.get("url", "")).query).get("id", [None])[0]
            if page_package != package:
                raise ValueError("Metadata package does not match requested app")
            text = self.driver.find_element(By.TAG_NAME, "body").text
            author = data.get("author") or {}
            rating = data.get("aggregateRating") or {}
            offers = data.get("offers") or []
            offer = (
                offers[0]
                if isinstance(offers, list) and offers
                else offers
                if isinstance(offers, dict)
                else {}
            )
            price = offer.get("price")
            return {
                "package": package,
                "metadata_status": "complete",
                "developer": author.get("name"),
                "description": data.get("description"),
                "rating": float(rating["ratingValue"])
                if rating.get("ratingValue") is not None
                else None,
                "rating_count": int(rating["ratingCount"])
                if rating.get("ratingCount") is not None
                else None,
                "price": float(price) if price is not None else None,
                "currency": offer.get("priceCurrency"),
                "ads_observed": True
                if "Chứa quảng cáo" in text or "Contains ads" in text
                else None,
                "iap_observed": True
                if "Mua trong ứng dụng" in text or "In-app purchases" in text
                else None,
                "fetched_at": datetime.now(UTC).isoformat(),
                "metadata_evidence": self.capture(package),
            }
        except Exception:
            try:
                self.capture(f"{package}-error")
            except Exception:
                LOG.exception("Could not capture metadata failure evidence")
            raise
