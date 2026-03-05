# TrustMRR Startup Scraper

Scrapes **all startup listings** from [trustmrr.com](https://trustmrr.com), stores them
in a structured **SQLite database** (`startups.db`), and generates a **Markdown analysis
report** (`STARTUPS_ANALYSIS.md`) that highlights the most profitable / copyable opportunities.

---

## Repository layout

```
.
├── scraper.py            # Main scraper – fetches all listings from TrustMRR
├── database.py           # SQLite persistence layer (schema + helpers)
├── generate_readme.py    # Reads the DB and writes STARTUPS_ANALYSIS.md
├── requirements.txt      # Python dependencies
├── tests/
│   └── test_scraper.py   # Unit tests (no network required)
└── STARTUPS_ANALYSIS.md  # Generated report (created after you run the pipeline)
```

---

## Quick start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

For JavaScript-heavy pages, also install the Playwright browser:

```bash
playwright install chromium
```

### 2. Scrape TrustMRR

```bash
python scraper.py
```

| Flag | Default | Description |
|------|---------|-------------|
| `--db PATH` | `startups.db` | Output SQLite database path |
| `--delay SECS` | `1.5` | Pause between requests (be polite!) |
| `--headless` | off | Use a real browser via Playwright (for JS-rendered pages) |
| `--limit N` | unlimited | Stop after N startups (useful for testing) |

**Examples:**

```bash
# Save to a custom path, use headless browser
python scraper.py --db data/startups.db --headless

# Quick test run (first 20 startups only)
python scraper.py --limit 20
```

### 3. Generate the analysis report

```bash
python generate_readme.py
```

This writes `STARTUPS_ANALYSIS.md` with:

- Summary statistics
- **Top opportunities** (scored by profitability + growth + price multiple)
- Most profitable startups
- Fastest-growing startups
- Best-value acquisitions (lowest price/earnings multiple)
- Full startup list with all metrics

```bash
# Custom paths
python generate_readme.py --db data/startups.db --out REPORT.md
```

---

## SQLite database schema

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | Auto-increment |
| `name` | TEXT | Startup name |
| `detail_url` | TEXT UNIQUE | TrustMRR listing URL |
| `description` | TEXT | Short description |
| `mrr` | REAL | Monthly Recurring Revenue (USD) |
| `arr` | REAL | Annual Recurring Revenue (USD) |
| `asking_price` | REAL | Listed asking price (USD) |
| `revenue` | REAL | Reported revenue (USD) |
| `profit` | REAL | Reported monthly profit (USD) |
| `growth_rate` | REAL | Growth rate (%) |
| `category` | TEXT | Business category / niche |
| `founded_year` | INTEGER | Year founded |
| `profit_multiple` | REAL | `asking_price / (profit × 12)` |
| `mrr_multiple` | REAL | `asking_price / mrr` |
| `scraped_at` | TEXT | ISO-8601 scrape timestamp |

### Useful queries

```sql
sqlite3 startups.db

-- All profitable startups
SELECT name, mrr, profit, growth_rate, asking_price
FROM startups WHERE profit > 0 ORDER BY profit DESC;

-- Cheapest deals (profit multiple ≤ 3)
SELECT name, profit_multiple, asking_price
FROM startups WHERE profit_multiple BETWEEN 0 AND 3
ORDER BY profit_multiple;

-- Fast-growing SaaS (>20 % MoM)
SELECT name, category, mrr, growth_rate
FROM startups WHERE growth_rate >= 20 ORDER BY growth_rate DESC;

-- Category breakdown
SELECT category, COUNT(*) AS n, AVG(mrr) AS avg_mrr
FROM startups GROUP BY category ORDER BY n DESC;
```

---

## Running the tests

```bash
python -m pytest tests/ -v
```

Tests cover all parsing helpers and database operations without any network access.

---

## How the scoring model works

The analysis report scores each startup on these criteria:

| Signal | Points |
|--------|--------|
| Positive profit | +20 |
| Growth ≥ 10 % | +15 |
| Growth ≥ 30 % | +10 (bonus) |
| Profit multiple ≤ 3× | +20 |
| MRR multiple ≤ 36× | +10 |
| Has MRR data | +10 |
| Has recurring revenue | +15 |
| Category filled in | +5 |

Startups that score highest represent the **most attractive business models to copy
in a new market or niche** — they are already proven profitable, growing fast, and
(where listed for sale) priced reasonably relative to earnings.