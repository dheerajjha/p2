"""
tests/test_scraper.py
=====================
Unit tests for the parsing helpers in scraper.py and the database layer in database.py.
No network access is required — all tests use fixtures and in-memory databases.
"""

import sqlite3
import sys
import os
import pytest
from bs4 import BeautifulSoup

# Allow imports from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scraper import (
    clean,
    parse_money,
    parse_pct,
    parse_card,
    parse_detail_page,
    _find_metric,
    _find_growth,
    _find_category,
    _find_year,
    get_all_listing_urls,
)
from database import StartupDatabase, _calc_profit_multiple, _calc_mrr_multiple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def in_memory_db(tmp_path) -> StartupDatabase:
    return StartupDatabase(str(tmp_path / "test.db"))


# ---------------------------------------------------------------------------
# parse_money
# ---------------------------------------------------------------------------

class TestParseMoney:
    def test_plain_integer(self):
        assert parse_money("1200") == 1200.0

    def test_dollar_sign(self):
        assert parse_money("$5,000") == 5000.0

    def test_k_suffix(self):
        assert parse_money("3.5K") == 3500.0

    def test_m_suffix(self):
        assert parse_money("2M") == 2_000_000.0

    def test_b_suffix(self):
        assert parse_money("1.5B") == 1_500_000_000.0

    def test_mixed_text(self):
        assert parse_money("MRR: $1,200/mo") == 1200.0

    def test_none_on_no_number(self):
        assert parse_money("no numbers here") is None

    def test_empty_string(self):
        assert parse_money("") is None

    def test_none_input(self):
        assert parse_money(None) is None


# ---------------------------------------------------------------------------
# parse_pct
# ---------------------------------------------------------------------------

class TestParsePct:
    def test_basic(self):
        assert parse_pct("15%") == 15.0

    def test_decimal(self):
        assert parse_pct("3.75%") == 3.75

    def test_in_sentence(self):
        assert parse_pct("Growing at 22.5% MoM") == 22.5

    def test_no_percent(self):
        assert parse_pct("no percent") is None

    def test_empty(self):
        assert parse_pct("") is None


# ---------------------------------------------------------------------------
# clean
# ---------------------------------------------------------------------------

class TestClean:
    def test_strips_whitespace(self):
        assert clean("  hello   world  ") == "hello world"

    def test_newlines(self):
        assert clean("line1\nline2\n  line3") == "line1 line2 line3"

    def test_none(self):
        assert clean(None) == ""


# ---------------------------------------------------------------------------
# _find_metric
# ---------------------------------------------------------------------------

class TestFindMetric:
    def test_mrr(self):
        assert _find_metric("MRR: $2,500/mo", ["mrr"]) == 2500.0

    def test_arr(self):
        assert _find_metric("ARR $30K", ["arr"]) == 30_000.0

    def test_missing_keyword(self):
        assert _find_metric("Revenue: $10K", ["mrr"]) is None

    def test_case_insensitive(self):
        assert _find_metric("Asking Price: $50,000", ["asking price"]) == 50_000.0


# ---------------------------------------------------------------------------
# _find_growth
# ---------------------------------------------------------------------------

class TestFindGrowth:
    def test_growth_keyword(self):
        assert _find_growth("30% growth YoY") == 30.0

    def test_mom(self):
        assert _find_growth("MoM: 12.5%") == 12.5

    def test_no_growth(self):
        assert _find_growth("no growth info here") is None


# ---------------------------------------------------------------------------
# _find_year
# ---------------------------------------------------------------------------

class TestFindYear:
    def test_founded(self):
        assert _find_year("Founded in 2021") == 2021

    def test_fallback(self):
        assert _find_year("Started 2019") == 2019

    def test_none(self):
        assert _find_year("no year") is None


# ---------------------------------------------------------------------------
# parse_card
# ---------------------------------------------------------------------------

class TestParseCard:
    def _make_card(self, name="Acme SaaS", desc="A great product", mrr="$2,500",
                   href="/startups/acme"):
        html = f"""
        <article>
          <h2><a href="{href}">{name}</a></h2>
          <p class="description">{desc}</p>
          <span class="mrr">MRR: {mrr}</span>
          <span class="badge">B2B SaaS</span>
        </article>
        """
        return make_soup(html).select_one("article")

    def test_name_extracted(self):
        card = self._make_card()
        result = parse_card(card, "https://trustmrr.com/")
        assert result is not None
        assert result["name"] == "Acme SaaS"

    def test_mrr_extracted(self):
        card = self._make_card(mrr="$3,000")
        result = parse_card(card, "https://trustmrr.com/")
        assert result is not None
        assert result["mrr"] == 3000.0

    def test_detail_url_extracted(self):
        card = self._make_card(href="/startups/acme-saas")
        result = parse_card(card, "https://trustmrr.com/")
        assert result is not None
        assert result["detail_url"] == "https://trustmrr.com/startups/acme-saas"

    def test_no_name_returns_none(self):
        soup = make_soup("<article><p>just text</p></article>").select_one("article")
        result = parse_card(soup, "https://trustmrr.com/")
        assert result is None

    def test_category_from_badge(self):
        card = self._make_card()
        result = parse_card(card, "https://trustmrr.com/")
        assert result is not None
        assert result["category"] == "B2B SaaS"


# ---------------------------------------------------------------------------
# parse_detail_page
# ---------------------------------------------------------------------------

class TestParseDetailPage:
    def test_basic_extraction(self):
        html = """
        <html>
        <head>
          <title>My Startup – TrustMRR</title>
          <meta name="description" content="A profitable B2B tool.">
        </head>
        <body>
          <h1>My Startup</h1>
          <p>MRR: $5,000. Profit: $2,000/mo. Growth: 20% MoM. Founded 2020.</p>
        </body>
        </html>
        """
        soup = make_soup(html)
        result = parse_detail_page(soup, "https://trustmrr.com/startups/my-startup")
        assert result is not None
        assert result["name"] == "My Startup"
        assert result["mrr"] == 5000.0
        assert result["profit"] == 2000.0
        assert result["growth_rate"] == 20.0
        assert result["founded_year"] == 2020

    def test_returns_none_without_name(self):
        soup = make_soup("<html><body><p>nothing here</p></body></html>")
        result = parse_detail_page(soup, "https://trustmrr.com/some-page")
        assert result is None


# ---------------------------------------------------------------------------
# get_all_listing_urls
# ---------------------------------------------------------------------------

class TestGetAllListingUrls:
    def test_detects_pagination(self):
        html = """
        <nav class="pagination">
          <a href="/?page=2">2</a>
          <a href="/?page=3">3</a>
        </nav>
        """
        soup = make_soup(html)
        urls = get_all_listing_urls(soup)
        assert "https://trustmrr.com/?page=2" in urls
        assert "https://trustmrr.com/?page=3" in urls

    def test_always_includes_homepage(self):
        soup = make_soup("<html></html>")
        urls = get_all_listing_urls(soup)
        assert urls[0] == "https://trustmrr.com/"


# ---------------------------------------------------------------------------
# StartupDatabase
# ---------------------------------------------------------------------------

class TestStartupDatabase:
    def test_upsert_and_count(self, tmp_path):
        db = in_memory_db(tmp_path)
        db.upsert_startup({
            "name": "WidgetCo",
            "detail_url": "https://trustmrr.com/startups/widgetco",
            "mrr": 4000.0,
            "profit": 1500.0,
            "asking_price": 60000.0,
        })
        assert db.count() == 1
        db.close()

    def test_upsert_updates_existing(self, tmp_path):
        db = in_memory_db(tmp_path)
        url = "https://trustmrr.com/startups/widgetco"
        db.upsert_startup({"name": "WidgetCo", "detail_url": url, "mrr": 1000.0})
        db.upsert_startup({"name": "WidgetCo", "detail_url": url, "mrr": 5000.0})
        assert db.count() == 1
        rows = db.all_startups()
        assert dict(rows[0])["mrr"] == 5000.0
        db.close()

    def test_profit_multiple_computed(self, tmp_path):
        db = in_memory_db(tmp_path)
        db.upsert_startup({
            "name": "ProfitCo",
            "detail_url": "https://trustmrr.com/startups/profitco",
            "profit": 1000.0,
            "asking_price": 36000.0,
        })
        rows = db.all_startups()
        assert dict(rows[0])["profit_multiple"] == 3.0  # 36000 / (1000 * 12)
        db.close()

    def test_mrr_multiple_computed(self, tmp_path):
        db = in_memory_db(tmp_path)
        db.upsert_startup({
            "name": "MrrCo",
            "detail_url": "https://trustmrr.com/startups/mrrco",
            "mrr": 2000.0,
            "asking_price": 48000.0,
        })
        rows = db.all_startups()
        assert dict(rows[0])["mrr_multiple"] == 24.0
        db.close()

    def test_profitable_startups_filter(self, tmp_path):
        db = in_memory_db(tmp_path)
        db.upsert_startup({
            "name": "ProfitCo",
            "detail_url": "https://trustmrr.com/s/a",
            "profit": 500.0,
        })
        db.upsert_startup({
            "name": "LossCo",
            "detail_url": "https://trustmrr.com/s/b",
            "profit": -200.0,
        })
        profitable = db.profitable_startups()
        assert len(profitable) == 1
        assert dict(profitable[0])["name"] == "ProfitCo"
        db.close()

    def test_top_by_growth(self, tmp_path):
        db = in_memory_db(tmp_path)
        for i, g in enumerate([5.0, 30.0, 15.0]):
            db.upsert_startup({
                "name": f"Startup{i}",
                "detail_url": f"https://trustmrr.com/s/{i}",
                "growth_rate": g,
            })
        top = db.top_by_growth(2)
        assert dict(top[0])["growth_rate"] == 30.0
        db.close()

    def test_best_value(self, tmp_path):
        db = in_memory_db(tmp_path)
        db.upsert_startup({
            "name": "CheapCo",
            "detail_url": "https://trustmrr.com/s/cheap",
            "profit": 1000.0,
            "asking_price": 24000.0,  # multiple = 2.0
        })
        db.upsert_startup({
            "name": "PricyCo",
            "detail_url": "https://trustmrr.com/s/pricey",
            "profit": 1000.0,
            "asking_price": 120000.0,  # multiple = 10.0
        })
        bv = db.best_value(max_multiple=4.0)
        names = [dict(r)["name"] for r in bv]
        assert "CheapCo" in names
        assert "PricyCo" not in names
        db.close()


# ---------------------------------------------------------------------------
# Internal multiple helpers
# ---------------------------------------------------------------------------

class TestMultipleHelpers:
    def test_profit_multiple(self):
        assert _calc_profit_multiple(36000, 1000) == 3.0

    def test_profit_multiple_none_when_zero_profit(self):
        assert _calc_profit_multiple(36000, 0) is None

    def test_profit_multiple_none_when_none(self):
        assert _calc_profit_multiple(None, 1000) is None

    def test_mrr_multiple(self):
        assert _calc_mrr_multiple(48000, 2000) == 24.0

    def test_mrr_multiple_none(self):
        assert _calc_mrr_multiple(None, None) is None
