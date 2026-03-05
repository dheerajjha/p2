#!/usr/bin/env python3
import argparse
import csv
import json
import math
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://trustmrr.com/api/v1/startups"


def fetch_json(url: str, headers: dict[str, str], retries: int = 3) -> dict[str, Any]:
    for attempt in range(retries + 1):
        req = Request(url, headers=headers)
        try:
            with urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in {429, 500} and attempt < retries:
                time.sleep(2 + attempt * 3)
                continue
            raise
        except URLError:
            if attempt < retries:
                time.sleep(2 + attempt * 2)
                continue
            raise
    raise RuntimeError(f"Unable to fetch data from {url}")


def to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_startup(item: dict[str, Any]) -> dict[str, Any]:
    revenue = item.get("revenue") or {}
    slug = item.get("slug")
    return {
        "slug": slug,
        "name": item.get("name"),
        "description": item.get("description"),
        "website": item.get("website"),
        "source_url": f"https://trustmrr.com/startup/{slug}" if slug else None,
        "country": item.get("country"),
        "founded_date": item.get("foundedDate"),
        "category": item.get("category"),
        "payment_provider": item.get("paymentProvider"),
        "target_audience": item.get("targetAudience"),
        "customers": to_int(item.get("customers")),
        "active_subscriptions": to_int(item.get("activeSubscriptions")),
        "mrr_cents": to_int(revenue.get("mrr")),
        "revenue_last_30d_cents": to_int(revenue.get("last30Days")),
        "revenue_total_cents": to_int(revenue.get("total")),
        "asking_price_cents": to_int(item.get("askingPrice")),
        "profit_margin_last_30d": to_float(item.get("profitMarginLast30Days")),
        "growth_30d": to_float(item.get("growth30d")),
        "multiple": to_float(item.get("multiple")),
        "on_sale": 1 if item.get("onSale") else 0,
        "first_listed_for_sale_at": item.get("firstListedForSaleAt"),
        "x_handle": item.get("xHandle"),
        "raw_json": json.dumps(item, separators=(",", ":"), ensure_ascii=False),
    }


def fetch_all_startups(api_key: str | None, page_size: int = 50, max_pages: int | None = None) -> list[dict[str, Any]]:
    page = 1
    startups: list[dict[str, Any]] = []
    headers = {
        "Accept": "application/json",
        "User-Agent": "p2-trustmrr-scraper/1.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    while True:
        params = urlencode({"page": page, "limit": page_size})
        payload = fetch_json(f"{API_BASE}?{params}", headers=headers)
        data = payload.get("data") or []
        startups.extend(normalize_startup(item) for item in data)

        has_more = bool((payload.get("meta") or {}).get("hasMore"))
        if max_pages is not None and page >= max_pages:
            break
        if not has_more:
            break
        page += 1
        time.sleep(0.75)

    return startups


def create_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS startups (
            slug TEXT PRIMARY KEY,
            name TEXT,
            description TEXT,
            website TEXT,
            source_url TEXT,
            country TEXT,
            founded_date TEXT,
            category TEXT,
            payment_provider TEXT,
            target_audience TEXT,
            customers INTEGER,
            active_subscriptions INTEGER,
            mrr_cents INTEGER,
            revenue_last_30d_cents INTEGER,
            revenue_total_cents INTEGER,
            asking_price_cents INTEGER,
            profit_margin_last_30d REAL,
            growth_30d REAL,
            multiple REAL,
            on_sale INTEGER NOT NULL DEFAULT 0,
            first_listed_for_sale_at TEXT,
            x_handle TEXT,
            raw_json TEXT NOT NULL,
            scraped_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_startups_on_sale ON startups(on_sale)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_startups_mrr ON startups(mrr_cents DESC)")


def save_sqlite(db_path: Path, startups: list[dict[str, Any]]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    scraped_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with sqlite3.connect(db_path) as conn:
        create_schema(conn)
        conn.executemany(
            """
            INSERT INTO startups (
                slug,name,description,website,source_url,country,founded_date,category,
                payment_provider,target_audience,customers,active_subscriptions,mrr_cents,
                revenue_last_30d_cents,revenue_total_cents,asking_price_cents,
                profit_margin_last_30d,growth_30d,multiple,on_sale,
                first_listed_for_sale_at,x_handle,raw_json,scraped_at
            ) VALUES (
                :slug,:name,:description,:website,:source_url,:country,:founded_date,:category,
                :payment_provider,:target_audience,:customers,:active_subscriptions,:mrr_cents,
                :revenue_last_30d_cents,:revenue_total_cents,:asking_price_cents,
                :profit_margin_last_30d,:growth_30d,:multiple,:on_sale,
                :first_listed_for_sale_at,:x_handle,:raw_json,:scraped_at
            )
            ON CONFLICT(slug) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                website=excluded.website,
                source_url=excluded.source_url,
                country=excluded.country,
                founded_date=excluded.founded_date,
                category=excluded.category,
                payment_provider=excluded.payment_provider,
                target_audience=excluded.target_audience,
                customers=excluded.customers,
                active_subscriptions=excluded.active_subscriptions,
                mrr_cents=excluded.mrr_cents,
                revenue_last_30d_cents=excluded.revenue_last_30d_cents,
                revenue_total_cents=excluded.revenue_total_cents,
                asking_price_cents=excluded.asking_price_cents,
                profit_margin_last_30d=excluded.profit_margin_last_30d,
                growth_30d=excluded.growth_30d,
                multiple=excluded.multiple,
                on_sale=excluded.on_sale,
                first_listed_for_sale_at=excluded.first_listed_for_sale_at,
                x_handle=excluded.x_handle,
                raw_json=excluded.raw_json,
                scraped_at=excluded.scraped_at
            """,
            [{**row, "scraped_at": scraped_at} for row in startups],
        )
        conn.commit()


def write_csv(csv_path: Path, startups: list[dict[str, Any]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "slug",
        "name",
        "description",
        "website",
        "source_url",
        "country",
        "founded_date",
        "category",
        "payment_provider",
        "target_audience",
        "customers",
        "active_subscriptions",
        "mrr_cents",
        "revenue_last_30d_cents",
        "revenue_total_cents",
        "asking_price_cents",
        "profit_margin_last_30d",
        "growth_30d",
        "multiple",
        "on_sale",
        "first_listed_for_sale_at",
        "x_handle",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        writer.writeheader()
        for startup in startups:
            writer.writerow({field: startup.get(field) for field in fields})


def copyability_score(startup: dict[str, Any]) -> float:
    mrr = (startup.get("mrr_cents") or 0) / 100
    growth = startup.get("growth_30d") or 0
    customers = startup.get("customers") or 0
    multiple = startup.get("multiple")

    score = 0.0
    if mrr > 0:
        score += min(math.log10(mrr + 1) * 25, 40)
    if growth > 0:
        score += min(growth * 120, 20)
    if customers > 0:
        score += min(math.log10(customers + 1) * 6, 12)

    if multiple is not None and multiple <= 48:
        score += 8
    if startup.get("on_sale"):
        score += 5

    if startup.get("category") in {"AI", "Developer Tools", "Marketing"}:
        score += 6

    return round(score, 2)


def select_copyable_startups(startups: list[dict[str, Any]], top_n: int = 15) -> list[dict[str, Any]]:
    filtered = []
    for startup in startups:
        mrr = startup.get("mrr_cents") or 0
        customers = startup.get("customers") or 0
        growth = startup.get("growth_30d") or 0
        if mrr < 50000 and customers < 100:
            continue
        if growth < -0.2:
            continue

        startup_with_score = dict(startup)
        startup_with_score["copyability_score"] = copyability_score(startup)
        filtered.append(startup_with_score)

    filtered.sort(key=lambda row: (row["copyability_score"], row.get("mrr_cents") or 0), reverse=True)
    return filtered[:top_n]


def format_money(cents: int | None) -> str:
    if cents is None:
        return "n/a"
    return f"${cents / 100:,.0f}"


def render_readme(readme_path: Path, startups: list[dict[str, Any]], picks: list[dict[str, Any]], db_path: Path) -> None:
    lines = [
        "# TrustMRR Startup Dataset",
        "",
        "This repository contains a scraper and SQLite export for startup data from https://trustmrr.com/.",
        "",
        "## Generated artifacts",
        "",
        f"- SQLite DB: `{db_path}`",
        "- CSV export: `output/trustmrr_startups.csv`",
        f"- Total startups captured: **{len(startups)}**",
        "",
        "## How to refresh",
        "",
        "```bash",
        "python scripts/scrape_trustmrr.py --db output/trustmrr_startups.sqlite --csv output/trustmrr_startups.csv",
        "```",
        "",
        "If your TrustMRR API access requires a token, set `TRUSTMRR_API_KEY` before running.",
        "",
        "## Copyable + profitable startup opportunities",
        "",
        "Heuristic: prioritizes startups with healthy MRR, enough customer demand, and non-negative growth.",
        "",
    ]

    if not picks:
        lines.extend(
            [
                "No qualifying startups were found in the current dataset.",
                "",
                "Re-run the scraper once API/network access is available.",
            ]
        )
    else:
        lines.extend(
            [
                "| Startup | Category | MRR | 30d Growth | Customers | Score |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for row in picks:
            growth_pct = (row.get("growth_30d") or 0) * 100
            lines.append(
                f"| [{row.get('name')}]({row.get('source_url')}) | {row.get('category') or 'n/a'} "
                f"| {format_money(row.get('mrr_cents'))} | {growth_pct:.1f}% "
                f"| {row.get('customers') or 0} | {row['copyability_score']:.2f} |"
            )

    readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape TrustMRR startups into SQLite and README summary")
    parser.add_argument("--api-key", default=None, help="TrustMRR API key. Defaults to TRUSTMRR_API_KEY env var if set.")
    parser.add_argument("--db", default="output/trustmrr_startups.sqlite", help="SQLite output path")
    parser.add_argument("--csv", default="output/trustmrr_startups.csv", help="CSV output path")
    parser.add_argument("--readme", default="README.md", help="README output path")
    parser.add_argument("--max-pages", type=int, default=None, help="Optional page limit for debugging")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = args.api_key
    if not api_key:
        from os import getenv

        api_key = getenv("TRUSTMRR_API_KEY")

    startups = fetch_all_startups(api_key=api_key, max_pages=args.max_pages)

    db_path = Path(args.db)
    csv_path = Path(args.csv)
    readme_path = Path(args.readme)

    save_sqlite(db_path, startups)
    write_csv(csv_path, startups)
    picks = select_copyable_startups(startups)
    render_readme(readme_path, startups, picks, db_path)

    print(f"Saved {len(startups)} startups to {db_path} and {csv_path}")
    print(f"Updated {readme_path} with {len(picks)} copyable startup picks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
