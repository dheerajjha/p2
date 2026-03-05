"""
TrustMRR.com Scraper
====================
Scrapes all startup listings from https://trustmrr.com/ and stores them
in a structured SQLite database (startups.db).

Usage:
    python scraper.py

Optional flags:
    --db PATH       Path to the SQLite database (default: startups.db)
    --delay SECS    Seconds to wait between page requests (default: 1.5)
    --headless      Use headless Playwright browser for JS-rendered pages
    --limit N       Stop after scraping N startups (default: unlimited)
"""

import argparse
import logging
import re
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from database import StartupDatabase

BASE_URL = "https://trustmrr.com"
DEFAULT_DELAY = 1.5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
)


def get_page(url: str, timeout: int = 20) -> Optional[BeautifulSoup]:
    """Fetch *url* and return a BeautifulSoup document, or None on error."""
    try:
        resp = SESSION.get(url, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.RequestException as exc:
        log.warning("Failed to fetch %s: %s", url, exc)
        return None


def get_page_playwright(url: str) -> Optional[BeautifulSoup]:
    """
    Fetch *url* using a headless Chromium browser via Playwright.
    Falls back when the site heavily relies on client-side rendering.
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30_000)
            html = page.content()
            browser.close()
        return BeautifulSoup(html, "lxml")
    except Exception as exc:  # noqa: BLE001
        log.warning("Playwright fetch failed for %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Text / value extraction helpers
# ---------------------------------------------------------------------------

_MONEY_RE = re.compile(r"[\$€£]?\s*([\d,]+(?:\.\d+)?)\s*([kKmMbB](?!\w))?")
_PCT_RE = re.compile(r"([\d.]+)\s*%")


def parse_money(text: str) -> Optional[float]:
    """
    Parse a money/number string like '$1,200', '3.5K', '2M' → float.
    Returns None if nothing recognisable is found.
    """
    if not text:
        return None
    m = _MONEY_RE.search(text.replace(",", ""))
    if not m:
        return None
    value = float(m.group(1))
    multiplier = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(
        (m.group(2) or "").lower(), 1
    )
    return value * multiplier


def parse_pct(text: str) -> Optional[float]:
    """Parse a percentage string like '12.5%' → 12.5."""
    if not text:
        return None
    m = _PCT_RE.search(text)
    return float(m.group(1)) if m else None


def clean(text: Optional[str]) -> str:
    """Strip and normalise whitespace."""
    return " ".join((text or "").split())


# ---------------------------------------------------------------------------
# Site-specific parsing
# ---------------------------------------------------------------------------

def discover_listing_pages(soup: BeautifulSoup) -> list[str]:
    """
    Return all pagination / listing URLs found on the homepage.
    Handles common patterns: ?page=N, /page/N, infinite-scroll anchor links.
    """
    pages: list[str] = []
    for a in soup.select("a[href]"):
        href = a["href"]
        full = urljoin(BASE_URL, href)
        parsed = urlparse(full)
        # Only keep URLs on the same host that look like pagination
        if parsed.netloc in ("trustmrr.com", "www.trustmrr.com") and (
            "page" in parsed.query.lower()
            or "/page/" in parsed.path
            or parsed.path.startswith("/startups")
            or parsed.path.startswith("/listings")
            or parsed.path.startswith("/companies")
        ):
            if full not in pages:
                pages.append(full)
    return pages


def extract_startups_from_listing(soup: BeautifulSoup, page_url: str) -> list[dict]:
    """
    Parse a listing page and return a list of raw startup dicts.
    Tries multiple CSS selector strategies to be resilient to layout changes.
    """
    startups: list[dict] = []

    # --- strategy 1: explicit card containers --------------------------------
    card_selectors = [
        "article",
        "[class*='card']",
        "[class*='listing']",
        "[class*='startup']",
        "[class*='company']",
        "[class*='item']",
        "li[class]",
    ]
    cards = []
    for sel in card_selectors:
        cards = soup.select(sel)
        if len(cards) >= 2:  # at least 2 results → likely the right selector
            log.debug("Card selector '%s' matched %d items on %s", sel, len(cards), page_url)
            break

    for card in cards:
        startup = parse_card(card, page_url)
        if startup:
            startups.append(startup)

    # --- strategy 2: follow detail-page links if no cards found ---------------
    if not startups:
        links = []
        for a in soup.select("a[href]"):
            href = urljoin(BASE_URL, a["href"])
            parsed = urlparse(href)
            if (
                parsed.netloc in ("trustmrr.com", "www.trustmrr.com")
                and parsed.path not in ("/", "")
                and href not in links
            ):
                links.append(href)
        log.info(
            "No cards found; found %d potential detail links on %s",
            len(links),
            page_url,
        )
        for link in links[:50]:  # guard against too many links
            detail_soup = get_page(link)
            if detail_soup:
                startup = parse_detail_page(detail_soup, link)
                if startup:
                    startups.append(startup)

    return startups


def parse_card(card, page_url: str) -> Optional[dict]:
    """
    Parse a single card element and return a startup dict, or None if the
    element does not look like a startup listing.
    """
    # Try to find the detail URL
    detail_url = None
    a_tags = card.select("a[href]")
    for a in a_tags:
        href = a.get("href", "")
        if href and not href.startswith("#"):
            detail_url = urljoin(BASE_URL, href)
            break

    # Name – first heading or strong text
    name = None
    for sel in ["h1", "h2", "h3", "h4", "[class*='name']", "[class*='title']", "strong"]:
        el = card.select_one(sel)
        if el:
            name = clean(el.get_text())
            break

    if not name:
        return None  # Can't identify a meaningful card

    # Description
    description = None
    for sel in ["p", "[class*='desc']", "[class*='summary']", "[class*='bio']"]:
        el = card.select_one(sel)
        if el:
            txt = clean(el.get_text())
            if len(txt) > 20:
                description = txt
                break

    # Metrics – look for MRR, ARR, revenue, asking price, profit, etc.
    text = card.get_text(" ", strip=True)
    mrr = _find_metric(text, ["mrr", "monthly recurring revenue", "monthly revenue"])
    arr = _find_metric(text, ["arr", "annual recurring revenue", "annual revenue"])
    asking_price = _find_metric(text, ["asking price", "price", "asking"])
    revenue = _find_metric(text, ["revenue", "rev"])
    profit = _find_metric(text, ["profit", "net profit", "income"])
    growth = _find_growth(text)
    category = _find_category(card)
    founded_year = _find_year(text)

    return {
        "name": name,
        "detail_url": detail_url,
        "description": description,
        "mrr": mrr,
        "arr": arr,
        "asking_price": asking_price,
        "revenue": revenue,
        "profit": profit,
        "growth_rate": growth,
        "category": category,
        "founded_year": founded_year,
        "source_page": page_url,
        "raw_text": text[:2000],
    }


def parse_detail_page(soup: BeautifulSoup, url: str) -> Optional[dict]:
    """Parse a startup detail/profile page."""
    # Title / name
    name = None
    for sel in ["h1", "h2", "[class*='title']", "[class*='name']", "title"]:
        el = soup.select_one(sel)
        if el:
            name = clean(el.get_text())
            if name:
                break

    if not name:
        return None

    text = soup.get_text(" ", strip=True)

    # Description from meta or first substantial paragraph
    description = None
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        description = clean(meta_desc["content"])
    else:
        for p in soup.select("p"):
            txt = clean(p.get_text())
            if len(txt) > 40:
                description = txt
                break

    return {
        "name": name,
        "detail_url": url,
        "description": description,
        "mrr": _find_metric(text, ["mrr", "monthly recurring revenue", "monthly revenue"]),
        "arr": _find_metric(text, ["arr", "annual recurring revenue", "annual revenue"]),
        "asking_price": _find_metric(text, ["asking price", "price", "asking"]),
        "revenue": _find_metric(text, ["revenue", "rev"]),
        "profit": _find_metric(text, ["profit", "net profit", "income"]),
        "growth_rate": _find_growth(text),
        "category": _find_category(soup),
        "founded_year": _find_year(text),
        "source_page": url,
        "raw_text": text[:2000],
    }


# ---------------------------------------------------------------------------
# Sub-helpers for metric extraction
# ---------------------------------------------------------------------------

_METRIC_PATTERN = re.compile(
    r"[\$€£]?\s*([\d,]+(?:\.\d+)?)\s*([kKmMbB](?!\w))?",
    re.IGNORECASE,
)

# Character windows used when searching for metrics near keywords
METRIC_SEARCH_WINDOW = 80   # chars after keyword to look for a money value
GROWTH_LOOKBEHIND = 20      # chars before growth keyword (e.g. "22.5% growth")
GROWTH_LOOKAHEAD = 60       # chars after growth keyword


def _find_metric(text: str, keywords: list[str]) -> Optional[float]:
    """
    Find a numeric metric near any of the given keywords in *text*.
    Returns the first parsed float found, or None.
    """
    lower = text.lower()
    for kw in keywords:
        idx = lower.find(kw)
        if idx == -1:
            continue
        # Look for a number in the ~METRIC_SEARCH_WINDOW characters following the keyword
        snippet = text[idx: idx + METRIC_SEARCH_WINDOW]
        val = parse_money(snippet)
        if val is not None:
            return val
    return None


def _find_growth(text: str) -> Optional[float]:
    """Extract a growth percentage near 'growth', 'MoM', 'YoY' etc."""
    lower = text.lower()
    for kw in ["growth", "mom", "yoy", "month over month", "year over year"]:
        idx = lower.find(kw)
        if idx == -1:
            continue
        snippet = text[max(0, idx - GROWTH_LOOKBEHIND): idx + GROWTH_LOOKAHEAD]
        pct = parse_pct(snippet)
        if pct is not None:
            return pct
    return None


def _find_category(soup_or_el) -> Optional[str]:
    """Attempt to find a category/tag label."""
    for sel in [
        "[class*='category']",
        "[class*='tag']",
        "[class*='label']",
        "[class*='badge']",
        "[class*='niche']",
        "[class*='type']",
    ]:
        el = soup_or_el.select_one(sel)
        if el:
            txt = clean(el.get_text())
            if 1 < len(txt) < 60:
                return txt
    return None


_YEAR_RE = re.compile(r"\b(20[0-1]\d|202[0-5])\b")


def _find_year(text: str) -> Optional[int]:
    """Extract the most plausible founding year from text."""
    lower = text.lower()
    idx = lower.find("founded")
    if idx != -1:
        snippet = text[idx: idx + 30]
        m = _YEAR_RE.search(snippet)
        if m:
            return int(m.group(1))
    # Fallback: first year-like number in text
    m = _YEAR_RE.search(text)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Pagination helper
# ---------------------------------------------------------------------------

def get_all_listing_urls(start_soup: BeautifulSoup) -> list[str]:
    """
    Build a complete list of listing page URLs by following pagination links
    and detecting the maximum page number.
    """
    urls: list[str] = [BASE_URL + "/"]

    # Try to find a pager / pagination element
    pager = (
        start_soup.select_one("[class*='pagination']")
        or start_soup.select_one("[class*='pager']")
        or start_soup.select_one("nav")
    )

    if pager:
        page_links = pager.select("a[href]")
        nums = []
        for a in page_links:
            href = a["href"]
            m = re.search(r"[?&/]page[=/]?(\d+)", href, re.IGNORECASE)
            if m:
                nums.append(int(m.group(1)))
        if nums:
            max_page = max(nums)
            log.info("Detected %d pages of listings", max_page)
            for p in range(2, max_page + 1):
                urls.append(f"{BASE_URL}/?page={p}")
        else:
            # Follow all links from the pager
            for a in page_links:
                full = urljoin(BASE_URL, a["href"])
                if full not in urls:
                    urls.append(full)
    else:
        # Also try API-style endpoints common on listing sites
        extra_urls = discover_listing_pages(start_soup)
        for u in extra_urls:
            if u not in urls:
                urls.append(u)

    return urls


# ---------------------------------------------------------------------------
# Main scraping entry-point
# ---------------------------------------------------------------------------

def scrape(
    db_path: str = "startups.db",
    delay: float = DEFAULT_DELAY,
    use_playwright: bool = False,
    limit: Optional[int] = None,
) -> int:
    """
    Scrape TrustMRR and persist results to *db_path*.
    Returns the total number of startups stored.
    """
    db = StartupDatabase(db_path)

    fetcher = get_page_playwright if use_playwright else get_page

    log.info("Fetching homepage: %s", BASE_URL)
    start_soup = fetcher(BASE_URL + "/")
    if start_soup is None:
        # Try with Playwright as fallback
        log.info("Falling back to Playwright for homepage …")
        start_soup = get_page_playwright(BASE_URL + "/")
    if start_soup is None:
        log.error("Could not fetch homepage. Aborting.")
        return 0

    listing_urls = get_all_listing_urls(start_soup)
    log.info("Will scrape %d listing page(s)", len(listing_urls))

    total_saved = 0
    all_startups: list[dict] = []

    for i, url in enumerate(listing_urls, 1):
        log.info("[%d/%d] Scraping listing: %s", i, len(listing_urls), url)
        soup = fetcher(url)
        if soup is None:
            continue

        startups = extract_startups_from_listing(soup, url)
        log.info("  Found %d startups on this page", len(startups))

        for s in startups:
            # Fetch detail page for richer data if we have a URL and didn't
            # already parse it as a detail page.
            if s.get("detail_url") and s["detail_url"] != url:
                time.sleep(delay * 0.5)
                detail_soup = fetcher(s["detail_url"])
                if detail_soup:
                    detail = parse_detail_page(detail_soup, s["detail_url"])
                    if detail:
                        # Merge: prefer detail page values when available
                        for key, val in detail.items():
                            if val is not None and s.get(key) is None:
                                s[key] = val

            db.upsert_startup(s)
            all_startups.append(s)
            total_saved += 1

            if limit and total_saved >= limit:
                log.info("Reached limit of %d startups. Stopping.", limit)
                db.close()
                return total_saved

        time.sleep(delay)

    db.close()
    log.info("Scraping complete. Stored %d startup records in '%s'.", total_saved, db_path)
    return total_saved


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape trustmrr.com into a SQLite database.")
    p.add_argument("--db", default="startups.db", help="Output SQLite database path.")
    p.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help="Seconds between requests (default: 1.5).",
    )
    p.add_argument(
        "--headless",
        action="store_true",
        help="Use Playwright headless browser (for JS-rendered pages).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Scrape at most N startups (for testing).",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    scrape(
        db_path=args.db,
        delay=args.delay,
        use_playwright=args.headless,
        limit=args.limit,
    )
