"""Google Play Store data provider using HTTP transport and evidence-based parsers."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from threading import BoundedSemaphore
from urllib.parse import urlencode

from casual_scout.models import Chart, HttpResult, ParsedChart
from casual_scout.providers.google_http import GoogleHttpClient
from casual_scout.providers.google_parser import parse_google_chart, parse_google_metadata

LOCALES: dict[str, str] = {
    "vn": "vi",
    "th": "th",
    "id": "id",
    "my": "en",
    "ph": "en",
    "sg": "en",
    "la": "en",
    "kh": "en",
    "us": "en",
}

BASE_RPC_URL = (
    "https://play.google.com/_/PlayStoreUi/data/batchexecute"
    "?rpcids=vyAe2&source-path=%2Fstore%2Fapps%2Fcategory%2FGAME_CASUAL"
    "&soc-app=121&soc-platform=1&soc-device=1&rt=c"
)

# Standard payload template with 100 items requested
# cluster token: [2, "{cluster}", "GAME_CASUAL"]
PAYLOAD_TEMPLATE = (
    "f.req=%5B%5B%5B%22vyAe2%22%2C%22%5B%5Bnull%2C%5B%5B8%2C%5B20%2C100%5D%5D%2C"
    "null%2Cnull%2C%5B96%2C108%2C72%2C100%2C27%2C177%2C183%2C222%2C8%2C57%2C169%2C"
    "110%2C11%2C184%2C16%2C1%2C139%2C152%2C194%2C165%2C68%2C163%2C211%2C9%2C71%2C"
    "31%2C176%2C195%2C12%2C64%2C151%2C320%2C150%2C148%2C113%2C104%2C55%2C56%2C145%2C"
    "32%2C34%2C10%2C122%5D%2C%5Bnull%2Cnull%2C%5B%5B%5B1%2Cnull%2C1%5D%2Cnull%2C"
    "%5B%5B%5B%5D%5D%5D%2Cnull%2Cnull%2Cnull%2Cnull%2C%5Bnull%2C2%5D%2Cnull%2Cnull%2C"
    "null%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C"
    "%5B1%5D%5D%2C%5Bnull%2C%5B%5B%5B%5D%5D%5D%2Cnull%2Cnull%2C%5B1%5D%5D%2C%5Bnull%2C"
    "%5B%5B%5B%5D%5D%5D%2Cnull%2C%5B1%5D%5D%2C%5Bnull%2C%5B%5B%5B%5D%5D%5D%5D%2Cnull%2C"
    "null%2Cnull%2Cnull%2C%5B%5B%5B%5B%5D%5D%5D%5D%2C%5B%5B%5B%5B%5D%5D%5D%5D%5D%2C"
    "%5B%5B%5B%5B7%2C285%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C"
    "69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C"
    "63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C96%5D%2C"
    "%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C"
    "123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C"
    "140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C108%5D%2C%5B%5B1%2C73%2C96%2C103%2C"
    "97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C"
    "14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C72%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C100%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C27%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C177%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C183%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C8%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C169%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C110%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C11%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C184%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C16%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C1%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C456%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C139%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C194%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C165%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C68%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C163%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C211%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C9%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C65%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C71%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C31%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C12%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C64%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C151%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C150%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C344%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C113%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C104%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C55%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C56%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C145%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C32%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C"
    "%5B%5B7%2C10%5D%2C%5B%5B1%2C73%2C96%2C103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C"
    "31%2C101%2C123%2C74%2C49%2C80%2C20%2C10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C"
    "183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%2C%5B%5B7%2C122%5D%2C%5B%5B1%2C73%2C96%2C"
    "103%2C97%2C58%2C50%2C92%2C52%2C112%2C69%2C19%2C31%2C101%2C123%2C74%2C49%2C80%2C20%2C"
    "10%2C14%2C79%2C43%2C42%2C139%2C63%2C169%2C95%2C183%2C140%2C155%2C156%2C189%2C152%5D%5D%5D%5D%5D%5D%2C"
    "null%2Cnull%2C%5B%5B%5B1%2C2%5D%2C%5B10%2C8%2C9%5D%5D%5D%5D%2C"
    "%5B2%2C%5C%22{cluster}%5C%22%2C%5C%22GAME_CASUAL%5C%22%5D%5D%5D%22%2Cnull%2C%22generic%22%5D%5D%5D&"
)

CLUSTER_MAP = {
    "top-free": "topselling_free",
    "top-grossing": "topgrossing",
}


def chart_url(chart: Chart) -> str:
    """Build the batchexecute RPC endpoint for a given Chart."""
    country = chart.country.lower()
    lang = LOCALES.get(country, "en")
    return f"{BASE_RPC_URL}&hl={lang}&gl={country.upper()}"


class GooglePlayProvider:
    """Provider for acquiring Google Play Casual charts and application metadata."""

    def __init__(self, client: GoogleHttpClient | None = None) -> None:
        self.client = client or GoogleHttpClient()
        self._requests = BoundedSemaphore(10)

    def fetch_chart(self, chart: Chart) -> tuple[HttpResult, ParsedChart]:
        if (
            chart.country.lower() not in LOCALES
            or chart.genre != "GAME_CASUAL"
            or chart.provider != "google"
            or chart.platform != "android"
            or chart.feed_type not in CLUSTER_MAP
        ):
            raise ValueError("unsupported Google chart identity")
        cluster = CLUSTER_MAP[chart.feed_type]
        payload = PAYLOAD_TEMPLATE.format(cluster=cluster)
        url = chart_url(chart)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "Referer": "https://play.google.com/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "X-Same-Domain": "1",
        }

        with self._requests:
            result = self.client.post(url, content=payload, headers=headers)
        if result.body and not result.error:
            parsed = parse_google_chart(result.body, chart)
        else:
            parsed = ParsedChart(
                chart=chart,
                entries=[],
                source_updated=None,
                quality="invalid",
                issues=[result.error or "empty response"],
            )

        return result, parsed

    def fetch_metadata(
        self, country: str, ids: list[str]
    ) -> list[tuple[HttpResult, dict[str, dict]]]:
        return list(self.iter_metadata(country, ids))

    def iter_metadata(
        self, country: str, ids: list[str]
    ) -> Iterator[tuple[HttpResult, dict[str, dict]]]:
        if not ids:
            return
        if country.lower() not in LOCALES:
            raise ValueError("unsupported Google market")

        lang = LOCALES.get(country.lower(), "en")
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": f"{lang}-{country.upper()},{lang};q=0.9",
        }

        def fetch_one(package: str) -> tuple[HttpResult, dict[str, dict]]:
            query = urlencode({"id": package, "gl": country.upper(), "hl": lang})
            url = f"https://play.google.com/store/apps/details?{query}"
            with self._requests:
                result = self.client.get(url, headers=headers)
            if result.body and not result.error:
                meta = parse_google_metadata(result.body, package)
            else:
                meta = {
                    "package": package,
                    "status": "partial",
                    "error": result.error or "empty response",
                    "name": None,
                    "developer": None,
                    "description": None,
                    "genres": [],
                    "average_rating": None,
                    "rating_count": None,
                    "price": None,
                    "currency": None,
                    "store_url": url,
                    "icon_url": None,
                    "installs": None,
                    "min_installs": None,
                    "has_ads": None,
                    "has_iap": None,
                }
            return result, {package: meta}

        unique_ids = list(dict.fromkeys(ids))
        with ThreadPoolExecutor(max_workers=min(10, len(unique_ids))) as executor:
            remaining = iter(unique_ids)
            pending = set()
            for _ in range(min(10, len(unique_ids))):
                pending.add(executor.submit(fetch_one, next(remaining)))
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    yield future.result()
                    package = next(remaining, None)
                    if package is not None:
                        pending.add(executor.submit(fetch_one, package))
