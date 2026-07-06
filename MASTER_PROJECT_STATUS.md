# Master Project Status

Last updated: 2026-07-06

---

## Connector Status Overview

| Connector | Status | Live calls | DB persistence | Modify? |
|---|---|---|---|---|
| eBay | live / closed / frozen | confirmed (production) | yes | no — frozen |
| CJ Dropshipping | live / active / closed | confirmed | yes | no — frozen |
| TikTok Ads | pending_access | none | none | no — awaiting approval |
| Google Trends | pending_access / application_submitted | none | none | no — awaiting approval |
| Amazon / Keepa | paused | none | none | no |
| AliExpress | paused | none | none | no |
| Reddit | paused | none | none | no |
| YouTube | paused | none | none | no |
| Meta | paused | none | none | no |

---

## eBay

| Field | Value |
|---|---|
| Status | `live` / closed / frozen |
| Live production verified | yes |
| Real data saved | yes — DB and `/export/products` |
| Environment | production |
| Credentials | `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` set locally in `backend/.env` |
| Freeze | **FROZEN — do not modify unless blocking bug** |

**What is live:** eBay Browse API with OAuth client credentials. Production environment active (`EBAY_ENVIRONMENT=production`, `EBAY_PRODUCTION_READY=true`). Products discovered via `/discovery/multisource` or `/sources/ebay/discover` are scored and saved to `products.db`.

**What is not available:** Source URLs not always returned by eBay Browse API for all item types.

---

## CJ Dropshipping

| Field | Value |
|---|---|
| Status | `active` / closed / frozen |
| Live calls confirmed | yes — `live_call_confirmed=true` |
| DB rows inserted | 5 confirmed (2026-07-05) |
| `CJ_API_TOKEN` | set in `backend/.env` (gitignored) |
| `CJ_REFRESH_TOKEN` | set in `backend/.env` (gitignored) |
| Token TTL | 180 days (access token), 180 days (refresh token) — per current CJ docs |
| Token renewal script | `python -m dotenv -f .env run -- python scripts/refresh_cj_token.py` |
| `sellPrice` mapping | `supplier_cost` — confirmed from live API (CJ charges dropshipper) |
| `retail_price` | `None` in live mode — `suggestSellPrice` not in list endpoint |
| `image_url` | populated from `productImage` |
| `product_weight_kg` | populated from `productWeight` (grams / 1000) |
| `source_url` | `None` — not returned by CJ API |
| Freeze | **CLOSED — do not modify unless scheduled Phase 2 or Phase 3** |

**Token first-time capture:**
```
# Windows clipboard (copy API Key first):
python -m dotenv -f .env run -- python scripts/get_cj_tokens_from_api_key.py

# Check availability without API call:
python scripts/get_cj_tokens_from_api_key.py --check
```

**Token renewal (before expiry):**
```
python -m dotenv -f .env run -- python scripts/refresh_cj_token.py
```

**Next scheduled phases (not started):**
- Phase 2 — retail price enrichment via `GET /v1/product/query?pid=` (detail endpoint)
- Phase 3 — shipping cost via `POST /v1/logistic/freightCalculate` (requires vid from variant endpoint)

---

## TikTok Ads

| Field | Value |
|---|---|
| Status | `pending_access` |
| Official path | TikTok Commercial Content API |
| Base URL | `https://open.tiktokapis.com` |
| Endpoint | `POST /v2/research/adlib/ad/query/` |
| Auth header | `Authorization: Bearer {token}` |
| Scope requested | `research.adlib.basic` |
| Organization | Zaryotech |
| App name | Zaryotech Product Discovery |
| Support ticket | submitted 2026-07-05 |
| Live calls confirmed | `false` |
| DB persistence | none |
| Freeze | **do not modify until TikTok Developer Support responds** |

**Blocker:** `commercial_content_api` product and `research.adlib.basic` scope not visible in TikTok Developer Portal. Support ticket submitted 2026-07-05. Awaiting TikTok response.

**Approval email to monitor:** TikTok Developer Support reply to the support ticket submitted on 2026-07-05.

---

## Google Trends

| Field | Value |
|---|---|
| Status | `pending_access` / application submitted |
| Official API | Google Trends API (alpha) — announced July 2025 |
| Application submitted | yes — 2026-07-06 |
| Submitted email | `admin@zaryotech.com` |
| Google Cloud project | `zaryotech-product-discovery` |
| Project name | Zaryotech Product Discovery |
| Organization type | Private company |
| Use case | Commercial |
| Feedback availability | Both email and video conference |
| Apply URL | `https://developers.google.com/search/apis/trends` |
| Confirmation received | "Thank you for your application! We'll notify you if you're accepted to Trends API alpha test." |
| pytrends | **NOT ALLOWED** |
| Scraping | **NOT ALLOWED** |
| Google Ads substitute | **NOT ALLOWED** |
| BigQuery substitute | **NOT an active path in this phase** |
| Live calls confirmed | `false` |
| DB persistence | none (signal-only source — will never persist products) |
| Freeze | **do not implement until official alpha invitation received at admin@zaryotech.com** |

**Approval email to monitor:** Google alpha invitation at `admin@zaryotech.com`.

---

## Backend startup

```
# From backend/ directory — always start with dotenv injection:
python -m dotenv -f .env run -- python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## GitHub state

| Commit | Description |
|---|---|
| `6ec2b0b` | Document Google Trends API Alpha application submission |
| `c537cdc` | Document CJ refresh token capture |
| `b317915` | Finalize CJ Dropshipping live connector and token lifecycle |
| `67fb03c` | Generalize discovery UI for multiple sources |
| `5076a1d` | Add project status documentation |
| `16b417b` | Add operator product export reports |

Branch: `main`. Working tree: clean (at time of last push).

---

## Approval emails to monitor

| Platform | Where to check | What triggers next action |
|---|---|---|
| TikTok Developer Support | Email from TikTok responding to support ticket (submitted 2026-07-05) | `commercial_content_api` scope becomes available in portal → set `TIKTOK_API_PROVIDER=commercial_content_api` + token → run `POST /sources/tiktok_ads/verify` |
| Google Trends API Alpha | `admin@zaryotech.com` (application submitted 2026-07-06) | Invitation email from Google → log in to docs with that email → confirm endpoint + auth → set `GOOGLE_TRENDS_OFFICIAL_ACCESS_MODE=confirmed` + credentials → implement connector |

---

## Freeze rules

| Connector | Rule |
|---|---|
| eBay | Frozen — live, complete. No changes unless a blocking production bug is confirmed. |
| CJ Dropshipping | Closed — active, live, tokens set. No changes until Phase 2 retail enrichment or Phase 3 shipping are scheduled. |
| TikTok Ads | Frozen — do not touch until TikTok Developer Support responds. |
| Google Trends | Frozen — do not implement until official alpha invitation received at admin@zaryotech.com. No pytrends, no scraping, no substitutes. |
| Amazon / Keepa / AliExpress / Reddit / YouTube / Meta | Paused — do not start. |

---

## Next allowed actions

1. **Monitor approval emails** — TikTok Developer Support + Google Trends alpha (see table above). All other connector work waits on these.
2. **CJ Phase 2** (when scheduled) — retail price enrichment via `GET /v1/product/query?pid=` per live product.
3. **CJ Phase 3** (when scheduled, after Phase 2) — shipping cost via CJ logistics endpoint.
4. **CJ token renewal** — run `refresh_cj_token.py` before 180-day expiry.
5. **eBay bug fixes only** — if a confirmed production bug surfaces.

---

## Blocked actions

- Do not implement Google Trends connector until alpha invitation received.
- Do not modify TikTok Ads until Developer Support responds.
- Do not use pytrends, web scraping, Google Ads, or BigQuery as Google Trends substitutes.
- Do not start Amazon, Keepa, AliExpress, Reddit, YouTube, or Meta connectors.
- Do not commit `backend/.env` — gitignored, contains live tokens.
- Do not print or expose `CJ_API_TOKEN`, `CJ_REFRESH_TOKEN`, `EBAY_CLIENT_SECRET`, or any token/secret in any context.

---

## Recommended next connector decision

**Postpone.** Do not decide on the next connector to implement until:
1. TikTok Developer Support responds (scope `research.adlib.basic` visibility confirmed or denied), and
2. Google Trends alpha invitation arrives (or a rejection/timeline update is received).

Both responses will clarify the actual available API paths. Choosing a third connector before those responses risks duplicate work or misaligned priorities.

No fallback connector is approved yet. If TikTok and Google approvals are delayed, a new connector decision must be made explicitly by the project owner before any implementation starts.

---

## Checkpoint files

| File | Covers |
|---|---|
| `CHECKPOINT_CJ_DROPSHIPPING.md` | CJ live status, token lifecycle, field audit, Phase 2/3 roadmap |
| `CHECKPOINT_TIKTOK_PENDING_ACCESS.md` | TikTok pending_access details, endpoint, scope, ticket date |
| `CHECKPOINT_GOOGLE_TRENDS_PENDING_ACCESS.md` | Google Trends alpha application, access rules, completion criteria |
| `MASTER_PROJECT_STATUS.md` | This file — cross-connector summary |
