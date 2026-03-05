"""
database.py – SQLite persistence layer for the TrustMRR scraper.

Schema
------
startups
    id              INTEGER PK
    name            TEXT NOT NULL
    detail_url      TEXT UNIQUE
    description     TEXT
    mrr             REAL        -- monthly recurring revenue (USD)
    arr             REAL        -- annual recurring revenue (USD)
    asking_price    REAL        -- listed asking price (USD)
    revenue         REAL        -- reported revenue (USD)
    profit          REAL        -- reported profit/net income (USD)
    growth_rate     REAL        -- growth rate as percentage (e.g. 15.0 = 15 %)
    category        TEXT        -- business category / niche
    founded_year    INTEGER
    source_page     TEXT        -- listing page where startup was found
    raw_text        TEXT        -- first 2000 chars of page text (debug)
    profit_multiple REAL        -- computed: asking_price / (profit * 12), if available
    mrr_multiple    REAL        -- computed: asking_price / mrr, if available
    scraped_at      TEXT        -- ISO-8601 timestamp
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS startups (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    detail_url      TEXT    UNIQUE,
    description     TEXT,
    mrr             REAL,
    arr             REAL,
    asking_price    REAL,
    revenue         REAL,
    profit          REAL,
    growth_rate     REAL,
    category        TEXT,
    founded_year    INTEGER,
    source_page     TEXT,
    raw_text        TEXT,
    profit_multiple REAL,
    mrr_multiple    REAL,
    scraped_at      TEXT    NOT NULL
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_name          ON startups (name);",
    "CREATE INDEX IF NOT EXISTS idx_mrr           ON startups (mrr);",
    "CREATE INDEX IF NOT EXISTS idx_asking_price  ON startups (asking_price);",
    "CREATE INDEX IF NOT EXISTS idx_growth_rate   ON startups (growth_rate);",
    "CREATE INDEX IF NOT EXISTS idx_category      ON startups (category);",
    "CREATE INDEX IF NOT EXISTS idx_profit_mult   ON startups (profit_multiple);",
    "CREATE INDEX IF NOT EXISTS idx_mrr_mult      ON startups (mrr_multiple);",
]


class StartupDatabase:
    """Thin wrapper around a SQLite connection for startup data."""

    def __init__(self, path: str = "startups.db") -> None:
        self._path = path
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._bootstrap()
        log.info("Database opened: %s", path)

    # ------------------------------------------------------------------
    # Schema bootstrap
    # ------------------------------------------------------------------

    def _bootstrap(self) -> None:
        cur = self._conn.cursor()
        cur.execute(_CREATE_TABLE)
        for stmt in _CREATE_INDEXES:
            cur.execute(stmt)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def upsert_startup(self, data: dict[str, Any]) -> int:
        """
        Insert or update a startup record.
        Uses *detail_url* as the natural key when available, otherwise *name*.
        Returns the rowid of the affected row.
        """
        now = datetime.now(timezone.utc).isoformat()
        data = dict(data)  # copy so we don't mutate caller's dict
        data["scraped_at"] = now

        # Compute derived multiples
        data["profit_multiple"] = _calc_profit_multiple(
            data.get("asking_price"), data.get("profit")
        )
        data["mrr_multiple"] = _calc_mrr_multiple(
            data.get("asking_price"), data.get("mrr")
        )

        columns = [
            "name", "detail_url", "description",
            "mrr", "arr", "asking_price", "revenue", "profit",
            "growth_rate", "category", "founded_year", "source_page",
            "raw_text", "profit_multiple", "mrr_multiple", "scraped_at",
        ]
        vals = {c: data.get(c) for c in columns}

        placeholders = ", ".join(f":{c}" for c in columns)
        updates = ", ".join(
            f"{c} = excluded.{c}"
            for c in columns
            if c not in ("name", "detail_url")
        )

        sql = f"""
            INSERT INTO startups ({', '.join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(detail_url)
            DO UPDATE SET {updates}
        """  # noqa: S608
        cur = self._conn.execute(sql, vals)
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def all_startups(self) -> list[sqlite3.Row]:
        """Return all rows ordered by MRR descending."""
        return self._conn.execute(
            "SELECT * FROM startups ORDER BY mrr DESC NULLS LAST"
        ).fetchall()

    def top_by_growth(self, n: int = 20) -> list[sqlite3.Row]:
        """Return top *n* startups by growth_rate."""
        return self._conn.execute(
            "SELECT * FROM startups WHERE growth_rate IS NOT NULL "
            "ORDER BY growth_rate DESC LIMIT ?",
            (n,),
        ).fetchall()

    def best_value(self, max_multiple: float = 3.0, n: int = 20) -> list[sqlite3.Row]:
        """
        Return startups with a profit multiple ≤ *max_multiple*,
        ordered by profit multiple ascending (cheapest relative to profit first).
        """
        return self._conn.execute(
            "SELECT * FROM startups WHERE profit_multiple IS NOT NULL "
            "AND profit_multiple > 0 AND profit_multiple <= ? "
            "ORDER BY profit_multiple ASC LIMIT ?",
            (max_multiple, n),
        ).fetchall()

    def profitable_startups(self) -> list[sqlite3.Row]:
        """Return all startups with positive profit, ordered by profit DESC."""
        return self._conn.execute(
            "SELECT * FROM startups WHERE profit > 0 ORDER BY profit DESC"
        ).fetchall()

    def count(self) -> int:
        """Return total number of records."""
        row = self._conn.execute("SELECT COUNT(*) FROM startups").fetchone()
        return row[0]

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()
        log.info("Database closed: %s", self._path)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _calc_profit_multiple(
    asking_price: Optional[float], profit: Optional[float]
) -> Optional[float]:
    """
    Annual profit multiple = asking_price / (monthly_profit * 12).
    Returns None if either value is missing or zero.
    """
    if asking_price and profit and profit > 0:
        return round(asking_price / (profit * 12), 2)
    return None


def _calc_mrr_multiple(
    asking_price: Optional[float], mrr: Optional[float]
) -> Optional[float]:
    """
    MRR multiple = asking_price / mrr.
    Returns None if either value is missing or zero.
    """
    if asking_price and mrr and mrr > 0:
        return round(asking_price / mrr, 2)
    return None
