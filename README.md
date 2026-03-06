# TrustMRR Startup Dataset

This repository contains a scraper and SQLite export for startup data from https://trustmrr.com/.

## Generated artifacts

- SQLite DB: `output/trustmrr_startups.sqlite`
- CSV export: `output/trustmrr_startups.csv`
- Total startups captured: **446**

## How to refresh

```bash
python scripts/scrape_trustmrr.py --db output/trustmrr_startups.sqlite --csv output/trustmrr_startups.csv
```

If your TrustMRR API access requires a token, set `TRUSTMRR_API_KEY` before running.

## Copyable + profitable startup opportunities

Heuristic: prioritizes startups with healthy MRR and non-negative growth. Customer count data is not available from public HTML; the customer minimum filter is skipped when this field is absent.

| Startup | Category | MRR | 30d Growth | Customers | Score |
|---|---|---:|---:|---:|---:|
| [Linkerflow](https://trustmrr.com/startup/linkerflow) | Marketing | $1,266 | 236.6% | 0 | 71.00 |
| [Speel.co](https://trustmrr.com/startup/speel-co) | n/a | $66,124 | 252.5% | 0 | 65.00 |
| [Lunchbreak](https://trustmrr.com/startup/lunchbreak) | Education | $51,396 | 24.8% | 0 | 65.00 |
| [Interactive Video SaaS](https://trustmrr.com/startup/interactive-video-saas) | n/a | $47,558 | 69.4% | 0 | 65.00 |
| [POST BRIDGE](https://trustmrr.com/startup/post-bridge) | n/a | $28,263 | 42.8% | 0 | 65.00 |
| [Plutio (Super Work AI)](https://trustmrr.com/startup/plutio-super-work-ai) | n/a | $21,816 | 26.6% | 0 | 65.00 |
| [Stealth Venture](https://trustmrr.com/startup/ryze-ai) | n/a | $18,404 | 157.8% | 0 | 65.00 |
| [Reddit Agency](https://trustmrr.com/startup/reddit-agency) | n/a | $15,018 | 940.0% | 0 | 65.00 |
| [SEO Automation Platform](https://trustmrr.com/startup/seo-automation-platform) | n/a | $14,296 | 20.7% | 0 | 65.00 |
| [Easy App Reports by Beyond Analytics](https://trustmrr.com/startup/easy-app-reports-by-beyond-analytics) | Analytics | $8,250 | 16.7% | 0 | 65.00 |
| [Tasy AI GmbH](https://trustmrr.com/startup/tasy-ai-gmbh) | n/a | $7,292 | 20.1% | 0 | 65.00 |
| [Catalister](https://trustmrr.com/startup/catalister) | n/a | $6,966 | 22.1% | 0 | 65.00 |
| [Pitchlo](https://trustmrr.com/startup/pitchlo) | n/a | $5,967 | 51.3% | 0 | 65.00 |
| [Private Location Intelligence Platform](https://trustmrr.com/startup/private-location-intelligence-platform) | SaaS | $5,930 | 69.7% | 0 | 65.00 |
| [TranslateMom](https://trustmrr.com/startup/translatemom) | n/a | $4,767 | 56.4% | 0 | 65.00 |
