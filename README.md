# TrustMRR Startup Dataset

This repo now includes a TrustMRR scraper that builds a structured SQLite database with all startup records exposed by TrustMRR's startup API.

## Scraper source

- `/home/runner/work/p2/p2/scripts/scrape_trustmrr.py`
- `/home/runner/work/p2/p2/tests/test_scrape_trustmrr.py`

## How to run

```bash
cd /home/runner/work/p2/p2
python scripts/scrape_trustmrr.py \
  --db output/trustmrr_startups.sqlite \
  --csv output/trustmrr_startups.csv \
  --readme README.md
```

If your TrustMRR access requires authentication, set:

```bash
export TRUSTMRR_API_KEY="<your_api_key>"
```

## Output artifacts

- `output/trustmrr_startups.sqlite`
  - Main table: `startups`
  - Indexed by `slug` (PK), `on_sale`, and `mrr_cents`
  - Contains raw API payload in `raw_json` + normalized analytics fields
- `output/trustmrr_startups.csv`
- README section "Copyable + profitable startup opportunities" (auto-generated)

## Copyable + profitable startup opportunities

This section is generated automatically from scraped startups using a heuristic that favors:

- non-trivial MRR and customer demand,
- non-negative 30-day growth,
- stronger buy/build economics (when sale multiple is attractive).

Run the scraper to refresh this list with the latest full TrustMRR dataset.
