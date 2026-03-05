"""
generate_readme.py – Analyse startups.db and write a STARTUPS_ANALYSIS.md
report that highlights the most copyable / profitable opportunities.

Usage:
    python generate_readme.py                        # uses startups.db
    python generate_readme.py --db path/to/db.sqlite
    python generate_readme.py --out CUSTOM_NAME.md
"""

import argparse
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from database import StartupDatabase

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# ---------------------------------------------------------------------------
# Scoring heuristic
# ---------------------------------------------------------------------------

SCORE_WEIGHTS = {
    "has_profit": 20,         # +20 if profit > 0
    "good_growth": 15,        # +15 if growth_rate >= 10 %
    "low_multiple": 20,       # +20 if profit_multiple <= 3.0
    "low_mrr_multiple": 10,   # +10 if mrr_multiple <= 36
    "recurring": 15,          # +15 if mrr or arr is set
    "category_bonus": 5,      # +5 if category filled in
    "has_mrr": 10,            # +10 if mrr > 0
    "very_high_growth": 10,   # +10 bonus if growth_rate >= 30 %
}


def score_startup(row: sqlite3.Row) -> int:
    """
    Return an integer score (higher = more attractive opportunity to copy).
    """
    d = dict(row)
    s = 0
    if d.get("profit") and d["profit"] > 0:
        s += SCORE_WEIGHTS["has_profit"]
    if d.get("growth_rate") and d["growth_rate"] >= 10:
        s += SCORE_WEIGHTS["good_growth"]
    if d.get("growth_rate") and d["growth_rate"] >= 30:
        s += SCORE_WEIGHTS["very_high_growth"]
    if d.get("profit_multiple") and 0 < d["profit_multiple"] <= 3.0:
        s += SCORE_WEIGHTS["low_multiple"]
    if d.get("mrr_multiple") and 0 < d["mrr_multiple"] <= 36:
        s += SCORE_WEIGHTS["low_mrr_multiple"]
    if d.get("mrr") and d["mrr"] > 0:
        s += SCORE_WEIGHTS["has_mrr"]
        s += SCORE_WEIGHTS["recurring"]
    elif d.get("arr") and d["arr"] > 0:
        s += SCORE_WEIGHTS["recurring"]
    if d.get("category"):
        s += SCORE_WEIGHTS["category_bonus"]
    return s


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_money(val: Optional[float]) -> str:
    if val is None:
        return "–"
    if val >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    if val >= 1_000:
        return f"${val / 1_000:.1f}K"
    return f"${val:,.0f}"


def fmt_pct(val: Optional[float]) -> str:
    return f"{val:.1f}%" if val is not None else "–"


def fmt_multiple(val: Optional[float]) -> str:
    return f"{val:.1f}x" if val is not None else "–"


def row_to_md_row(row: sqlite3.Row, score: Optional[int] = None) -> str:
    d = dict(row)
    name = d.get("name") or "Unknown"
    url = d.get("detail_url") or ""
    name_cell = f"[{name}]({url})" if url else name
    mrr = fmt_money(d.get("mrr"))
    asking = fmt_money(d.get("asking_price"))
    profit = fmt_money(d.get("profit"))
    growth = fmt_pct(d.get("growth_rate"))
    mult = fmt_multiple(d.get("profit_multiple"))
    cat = d.get("category") or "–"
    score_cell = str(score) if score is not None else ""
    if score_cell:
        return f"| {name_cell} | {cat} | {mrr} | {profit} | {growth} | {asking} | {mult} | {score_cell} |"
    return f"| {name_cell} | {cat} | {mrr} | {profit} | {growth} | {asking} | {mult} |"


# ---------------------------------------------------------------------------
# Main report generator
# ---------------------------------------------------------------------------

def generate(db_path: str = "startups.db", out_path: str = "STARTUPS_ANALYSIS.md") -> None:
    db = StartupDatabase(db_path)
    total = db.count()

    if total == 0:
        log.warning(
            "Database '%s' is empty. Run scraper.py first to populate it.", db_path
        )
        db.close()
        return

    all_rows = db.all_startups()
    profitable = db.profitable_startups()
    top_growth = db.top_by_growth(20)
    best_value = db.best_value(max_multiple=4.0, n=20)

    # Score and sort all rows
    scored = sorted(
        [(row, score_startup(row)) for row in all_rows],
        key=lambda x: x[1],
        reverse=True,
    )
    top_opportunities = scored[:30]

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = []
    a = lines.append

    a("# TrustMRR Startup Opportunities Analysis")
    a("")
    a(f"> **Generated:** {now_str}  |  **Source:** {db_path}  |  **Total startups scraped:** {total}")
    a("")
    a(
        "This report identifies startups from [TrustMRR.com](https://trustmrr.com) that are "
        "most attractive to **copy or build profitably**. The scoring model considers "
        "profitability, growth rate, asking price multiples, and recurring revenue."
    )
    a("")
    a("---")
    a("")
    a("## 📊 Summary Statistics")
    a("")

    # Quick stats
    mrr_vals = [dict(r).get("mrr") for r in all_rows if dict(r).get("mrr")]
    profit_vals = [dict(r).get("profit") for r in all_rows if dict(r).get("profit") and dict(r)["profit"] > 0]
    price_vals = [dict(r).get("asking_price") for r in all_rows if dict(r).get("asking_price")]
    growth_vals = [dict(r).get("growth_rate") for r in all_rows if dict(r).get("growth_rate")]

    a("| Metric | Value |")
    a("|--------|-------|")
    a(f"| Total startups scraped | **{total}** |")
    a(f"| With positive profit | **{len(profitable)}** |")
    a(f"| With MRR data | **{len(mrr_vals)}** |")
    a(f"| With asking price | **{len(price_vals)}** |")
    a(f"| Average MRR | **{fmt_money(sum(mrr_vals)/len(mrr_vals) if mrr_vals else None)}** |")
    a(f"| Median asking price | **{fmt_money(sorted(price_vals)[len(price_vals)//2] if price_vals else None)}** |")
    a(f"| Avg growth rate | **{fmt_pct(sum(growth_vals)/len(growth_vals) if growth_vals else None)}** |")
    a("")
    a("---")
    a("")
    a("## 🏆 Top Opportunities to Copy (Scored)")
    a("")
    a(
        "Startups below score highest on our opportunity matrix: profitable, growing fast, "
        "and priced cheaply relative to earnings. These represent business *models* worth "
        "replicating in a new market or niche."
    )
    a("")
    a("| Startup | Category | MRR | Monthly Profit | Growth | Asking Price | P/E Multiple | Score |")
    a("|---------|----------|-----|----------------|--------|-------------|-------------|-------|")
    for row, sc in top_opportunities:
        a(row_to_md_row(row, sc))
    a("")
    a("---")
    a("")
    a("## 💸 Most Profitable Startups")
    a("")
    a("| Startup | Category | MRR | Monthly Profit | Growth | Asking Price | P/E Multiple |")
    a("|---------|----------|-----|----------------|--------|-------------|-------------|")
    for row in profitable[:30]:
        a(row_to_md_row(row))
    a("")
    a("---")
    a("")
    a("## 📈 Fastest Growing Startups")
    a("")
    a("| Startup | Category | MRR | Monthly Profit | Growth | Asking Price | P/E Multiple |")
    a("|---------|----------|-----|----------------|--------|-------------|-------------|")
    for row in top_growth:
        a(row_to_md_row(row))
    a("")
    a("---")
    a("")
    a("## 💰 Best Value Acquisitions (Low Price/Earnings Multiple)")
    a("")
    a(
        "Startups where the asking price is ≤ 4× annual profit — "
        "these may be underpriced and offer a quick path to ROI."
    )
    a("")
    a("| Startup | Category | MRR | Monthly Profit | Growth | Asking Price | P/E Multiple |")
    a("|---------|----------|-----|----------------|--------|-------------|-------------|")
    for row in best_value:
        a(row_to_md_row(row))
    a("")
    a("---")
    a("")
    a("## 📋 Full Startup List")
    a("")
    a("All scraped startups, ordered by MRR descending.")
    a("")
    a("| Startup | Category | MRR | Monthly Profit | Growth | Asking Price | P/E Multiple |")
    a("|---------|----------|-----|----------------|--------|-------------|-------------|")
    for row in all_rows:
        a(row_to_md_row(row))
    a("")
    a("---")
    a("")
    a("## 🔬 How to Use This Data")
    a("")
    a("```sql")
    a("-- Open the database")
    a("sqlite3 startups.db")
    a("")
    a("-- Top profitable startups")
    a("SELECT name, mrr, profit, growth_rate, asking_price")
    a("FROM startups WHERE profit > 0 ORDER BY profit DESC LIMIT 20;")
    a("")
    a("-- Cheap deals (profit multiple ≤ 3)")
    a("SELECT name, profit_multiple, asking_price")
    a("FROM startups WHERE profit_multiple BETWEEN 0 AND 3 ORDER BY profit_multiple;")
    a("")
    a("-- Fast-growing SaaS")
    a("SELECT name, category, mrr, growth_rate")
    a("FROM startups WHERE growth_rate >= 20 ORDER BY growth_rate DESC;")
    a("```")
    a("")
    a("---")
    a("")
    a("*Data scraped from [TrustMRR.com](https://trustmrr.com). "
      "All figures are as reported on the site and may be self-reported by sellers.*")

    db.close()

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    log.info("Report written to '%s' (%d lines).", out_path, len(lines))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a Markdown analysis report from the scraped startup database."
    )
    p.add_argument("--db", default="startups.db", help="Path to the SQLite database.")
    p.add_argument(
        "--out",
        default="STARTUPS_ANALYSIS.md",
        help="Output Markdown file (default: STARTUPS_ANALYSIS.md).",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    generate(db_path=args.db, out_path=args.out)
