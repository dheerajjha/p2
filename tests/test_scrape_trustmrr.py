import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.scrape_trustmrr import (
    copyability_score,
    normalize_startup,
    save_sqlite,
    select_copyable_startups,
)


class TrustMrrScraperTests(unittest.TestCase):
    def test_normalize_startup_handles_basic_payload(self):
        payload = {
            "slug": "acme",
            "name": "Acme",
            "onSale": True,
            "revenue": {"mrr": 123400, "last30Days": 110000, "total": 500000},
            "growth30d": 0.11,
            "customers": 220,
        }

        normalized = normalize_startup(payload)

        self.assertEqual(normalized["slug"], "acme")
        self.assertEqual(normalized["mrr_cents"], 123400)
        self.assertEqual(normalized["on_sale"], 1)
        self.assertIn('"slug":"acme"', normalized["raw_json"])

    def test_select_copyable_startups_filters_declining_small_startups(self):
        startups = [
            {
                "slug": "good",
                "name": "Good",
                "mrr_cents": 300000,
                "customers": 300,
                "growth_30d": 0.1,
                "multiple": 24,
                "on_sale": 1,
                "category": "AI",
            },
            {
                "slug": "bad",
                "name": "Bad",
                "mrr_cents": 10000,
                "customers": 20,
                "growth_30d": -0.3,
                "multiple": None,
                "on_sale": 0,
                "category": "Other",
            },
        ]

        picks = select_copyable_startups(startups, top_n=10)

        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["slug"], "good")
        self.assertGreater(copyability_score(picks[0]), 0)

    def test_save_sqlite_creates_and_upserts_rows(self):
        rows = [
            {
                "slug": "x",
                "name": "X",
                "description": "desc",
                "website": "https://x.test",
                "source_url": "https://trustmrr.com/startup/x",
                "country": "US",
                "founded_date": "2024-01-01",
                "category": "Marketing",
                "payment_provider": "Stripe",
                "target_audience": "SMB",
                "customers": 10,
                "active_subscriptions": 8,
                "mrr_cents": 20000,
                "revenue_last_30d_cents": 18000,
                "revenue_total_cents": 80000,
                "asking_price_cents": 500000,
                "profit_margin_last_30d": 0.5,
                "growth_30d": 0.02,
                "multiple": 25.0,
                "on_sale": 1,
                "first_listed_for_sale_at": None,
                "x_handle": None,
                "raw_json": "{}",
            }
        ]

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "startups.sqlite"
            save_sqlite(db_path, rows)
            rows[0]["name"] = "X2"
            save_sqlite(db_path, rows)

            with sqlite3.connect(db_path) as conn:
                result = conn.execute("SELECT COUNT(*), MAX(name) FROM startups").fetchone()

            self.assertEqual(result[0], 1)
            self.assertEqual(result[1], "X2")


if __name__ == "__main__":
    unittest.main()
