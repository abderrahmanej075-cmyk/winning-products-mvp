# Project Status — Winning Products MVP

**Last verified:** 2026-07-02  
**Verification result:** All checks passed. Git status clean.

---

## Current Workflow

```
Discover → Deduplicate → Save to DB → Display → Filter/Sort
       → Shortlist → Review Notes/Decision → Pipeline → Export
```

| Step | Where |
|---|---|
| **Discover** | eBay Browse API (production). Seeds + country → scored candidates |
| **Deduplicate** | Backend deduplication on name before saving |
| **Save to DB** | SQLite via `/discovery/multisource` — persists all source-agnostic fields |
| **Display** | "Discovered eBay Products" table in frontend |
| **Filter / Sort** | By recommendation, country, eBay link, shortlist status; sort by newest / score / price |
| **Shortlist** | Star toggle per product → `POST /products/{pid}/shortlist` |
| **Review Notes / Decision Status** | Notes + status select in "Shortlisted Products" section |
| **Product Review Pipeline** | Kanban grouped by `review_status`: New → Researching → Test Candidate → Winner → Rejected |
| **Export Reports** | `GET /export/products?filter=...&format=json|csv` — downloadable from Operator Reports panel |

---

## Active Sources

| Source | Status | Notes |
|---|---|---|
| **eBay** | Production active | First working source. Uses eBay Browse API OAuth with production credentials. Falls back to stub if credentials absent. |
| Others | Planned | Architecture is source-agnostic. Additional sources plug in without changing review/export/pipeline. |

---

## Source-Agnostic Product Fields

These fields are set regardless of which source discovered the product:

| Field | Description |
|---|---|
| `source` | Origin source name (e.g. `"ebay"`) |
| `source_url` | Direct link to the original listing |
| `discovered_at` | ISO timestamp when the product was first saved |
| `shortlisted` | `0` or `1` — operator starred this product |
| `shortlisted_at` | ISO timestamp when shortlisted |
| `review_status` | `new` / `researching` / `test_candidate` / `winner` / `rejected` |
| `operator_notes` | Free-text notes saved per product |
| `reviewed_at` | ISO timestamp when last review field was updated |

---

## Key Backend Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Returns `{"status":"ok"}` — liveness check |
| `/products` | GET | All saved products with scores and review fields |
| `/discovery/multisource` | POST | Run discovery, deduplicate, score, save to DB |
| `/products/{pid}/shortlist` | POST | Toggle shortlisted flag |
| `/products/{pid}/review` | PATCH | Update `review_status` and/or `operator_notes` |
| `/export/products` | GET | Download products as JSON or CSV (`filter` + `format` params) |
| `/reports/daily/delivery/health` | GET | Report delivery layer health |
| `/sources/connectors/health` | GET | Source connector readiness plan |

**Export filters:** `shortlisted`, `winner`, `test_candidate`, `reviewed`, `all`  
**Export formats:** `json` (default), `csv`

---

## Frontend Sections

| Section | Purpose |
|---|---|
| **eBay Discovery** | Search input (seeds + country), triggers discovery, shows candidate count |
| **Discovered Products** | Filterable/sortable table of all eBay-sourced products with star toggle |
| **Shortlisted Products** | Cards for shortlisted products with review status select and notes field |
| **Product Review Pipeline** | Kanban columns by review status; drag via status select on each card |
| **Operator Reports** | Download buttons: 5 filter types × 2 formats (JSON + CSV) |
| **Sample / Manual Products** | Non-eBay products (manually added via form) |

---

## Verified Product Counts (2026-07-02)

| Category | Count |
|---|---|
| All products | 62 |
| eBay-sourced | 28 |
| Manual / sample | 34 |
| Shortlisted | 2 |
| Reviewed (reviewed_at set) | 3 |
| Winners | 0 |
| Test candidates | 0 |

---

## Safety Rules

- Never commit `.env` — credentials stay local only
- Never print secrets, tokens, or `.env` contents in any tool or log
- Keep review, pipeline, and export features source-agnostic — no eBay-specific logic in those layers
- Never use `git add .` or `git add -A` — always stage files explicitly by name
- Never push, tag, or force-push without explicit operator instruction

---

## Recommended Next Phase

The core workflow (discover → review → export) is complete and verified.

**Recommended before adding features:**
1. Run a code review pass (e.g. `/code-review ultra`) to catch tech debt before the codebase grows
2. OR add the next product source (e.g. AliExpress, Amazon) — the source-agnostic architecture is ready

**Do not do both at once.** Pick one next step, verify it passes, then proceed.
