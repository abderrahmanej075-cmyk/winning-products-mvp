# Master Project Status

Last updated: 2026-07-07 (Phase A field/schema review complete)

---

## Connector Status Overview

| Connector | Status | Live calls | DB persistence | Modify? |
|---|---|---|---|---|
| eBay | live / closed / frozen | confirmed (production) | yes | no  -  frozen |
| CJ Dropshipping | live / active / closed | confirmed | yes | no  -  frozen |
| TikTok Ads | pending_access | none | none | no  -  awaiting approval |
| Google Trends | pending_access / application_submitted | none | none | no  -  awaiting approval |
| Amazon / Keepa | paused | none | none | no |
| AliExpress | paused | none | none | no |
| Reddit | paused | none | none | no |
| YouTube Data API | official_audit / proceed_to_setup / pending_owner_approval | none | none | no  -  not approved |
| Meta Ad Library | audit_only / postponed | none | none | no  -  not approved |

---

## eBay

| Field | Value |
|---|---|
| Status | `live` / closed / frozen |
| Live production verified | yes |
| Real data saved | yes  -  DB and `/export/products` |
| Environment | production |
| Credentials | `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` set locally in `backend/.env` |
| Freeze | **FROZEN  -  do not modify unless blocking bug** |

**What is live:** eBay Browse API with OAuth client credentials. Production environment active (`EBAY_ENVIRONMENT=production`, `EBAY_PRODUCTION_READY=true`). Products discovered via `/discovery/multisource` or `/sources/ebay/discover` are scored and saved to `products.db`.

**What is not available:** Source URLs not always returned by eBay Browse API for all item types.

---

## CJ Dropshipping

| Field | Value |
|---|---|
| Status | `active` / closed / frozen |
| Live calls confirmed | yes  -  `live_call_confirmed=true` |
| DB rows inserted | 5 confirmed (2026-07-05) |
| `CJ_API_TOKEN` | set in `backend/.env` (gitignored) |
| `CJ_REFRESH_TOKEN` | set in `backend/.env` (gitignored) |
| Token TTL | 180 days (access token), 180 days (refresh token)  -  per current CJ docs |
| Token renewal script | `python -m dotenv -f .env run -- python scripts/refresh_cj_token.py` |
| `sellPrice` mapping | `supplier_cost`  -  confirmed from live API (CJ charges dropshipper) |
| `retail_price` | `None` in live mode  -  `suggestSellPrice` not in list endpoint |
| `image_url` | populated from `productImage` |
| `product_weight_kg` | populated from `productWeight` (grams / 1000) |
| `source_url` | `None`  -  not returned by CJ API |
| Freeze | **CLOSED  -  do not modify unless scheduled Phase 2 or Phase 3** |

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
- Phase 2  -  retail price enrichment via `GET /v1/product/query?pid=` (detail endpoint)
- Phase 3  -  shipping cost via `POST /v1/logistic/freightCalculate` (requires vid from variant endpoint)

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
| Official API | Google Trends API (alpha)  -  announced July 2025 |
| Application submitted | yes  -  2026-07-06 |
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
| DB persistence | none (signal-only source  -  will never persist products) |
| Freeze | **do not implement until official alpha invitation received at admin@zaryotech.com** |

**Approval email to monitor:** Google alpha invitation at `admin@zaryotech.com`.

---

## YouTube Data API

| Field | Value |
|---|---|
| Status | `official_audit` / proceed_to_setup / pending_owner_approval |
| Official API | YouTube Data API v3  -  `GET /search`, `GET /videos` |
| official_api | `true` |
| implementation_approved | `false` |
| no API calls made | `true` |
| no connector logic changed | `true` |
| Live calls confirmed | `false` |
| DB persistence | none (signal-only  -  no videos ever saved) |
| Access path | Google Cloud project + enable YouTube Data API v3 + API key (no OAuth, no approval queue) |
| Billing | not identified as required in official docs for default quota; confirm in GCP Console during setup |
| Quota | 100 `search.list` calls/day; 10,000 units/day for `videos.list` and other endpoints |
| Next action | Owner approves setup -> enable API in `zaryotech-product-discovery` -> generate API key -> implement connector |
| Scraping | **NOT ALLOWED** |
| Unofficial clients | **NOT ALLOWED** |

---

## Meta Ad Library

| Field | Value |
|---|---|
| Status | `audit_only` / postponed / not_approved_for_implementation |
| Official API | Meta Ad Library API (`GET /ads_archive`, Graph API v25.0) |
| official_api | `true` |
| implementation_approved | `false` |
| Live calls confirmed | `false` |
| DB persistence | none |
| Reason for postpone | Official API is limited for dropshipping product discovery: no spend/impressions data for product ads; EU geographic restriction hides US-only advertisers; not suitable as next primary source |
| Next action | Audit YouTube Data API before any new connector decision |
| Scraping | **NOT ALLOWED** |
| Unofficial clients | **NOT ALLOWED** |

---

## Backend startup

```
# From backend/ directory  -  always start with dotenv injection:
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
| TikTok Developer Support | Email from TikTok responding to support ticket (submitted 2026-07-05) | `commercial_content_api` scope becomes available in portal -> set `TIKTOK_API_PROVIDER=commercial_content_api` + token -> run `POST /sources/tiktok_ads/verify` |
| Google Trends API Alpha | `admin@zaryotech.com` (application submitted 2026-07-06) | Invitation email from Google -> log in to docs with that email -> confirm endpoint + auth -> set `GOOGLE_TRENDS_OFFICIAL_ACCESS_MODE=confirmed` + credentials -> implement connector |

---

## Freeze rules

| Connector | Rule |
|---|---|
| eBay | Frozen  -  live, complete. No changes unless a blocking production bug is confirmed. |
| CJ Dropshipping | Closed  -  active, live, tokens set. No changes until Phase 2 retail enrichment or Phase 3 shipping are scheduled. |
| TikTok Ads | Frozen  -  do not touch until TikTok Developer Support responds. |
| Google Trends | Frozen  -  do not implement until official alpha invitation received at admin@zaryotech.com. No pytrends, no scraping, no substitutes. |
| Meta Ad Library | Postponed  -  audit complete, not approved for implementation. Official API is limited for dropshipping product discovery (EU restriction, no spend/impressions for product ads). |
| YouTube Data API | official_audit complete / proceed_to_setup / pending_owner_approval  -  no implementation yet. |
| Amazon / Keepa / AliExpress / Reddit | Paused  -  do not start. |

---

## Current decision point

Product Decision Engine plan is complete. See PRODUCT_DECISION_ENGINE_PLAN.md.
Phase A (field/schema review) is complete. See FIELD_SCHEMA_REVIEW.md.
Phase B (backend-only decision engine) = COMMITTED (8006d40) / runtime smoke test passed.
  backend/decision_engine.py, backend/main.py, backend/test_decision_engine.py committed.
  51 tests pass. /products and /export/products include all 8 decision fields.
  /products/{pid} unchanged. No DB migration. No connector changes. No external APIs.
  backend/.env not modified or printed. No secrets exposed.
Phase B runtime smoke test = PASSED (2026-07-08).
  76 products: NEEDS_ENRICHMENT=48, REJECT=28, WATCH=0, TEST=0.
  Top missing fields: image_url=71, shipping_cost=42, supplier_cost=40.
  See DECISION_OUTPUT_AUDIT.md for full breakdown.
DECISION_OUTPUT_AUDIT.md = created / pipeline audit complete / pending owner review.
  Audit identifies eBay image_url + item_id pipeline gap as highest-ROI next investigation.
  CJ Phase 2 retail enrichment is next confirmed-scoped action for CJ products.
EBAY_IMAGE_PIPELINE_AUDIT.md = created / root cause confirmed / no implementation started.
  Root cause confirmed: Category A - _ebay_item_to_raw() in sources/ebay.py never extracts
    itemId or image.imageUrl from the eBay Browse API response.
  Secondary: upsert_discovered_candidate() INSERT-only; existing rows not updated by re-discovery.
  item_id recoverable from source_url (stored) without API call.
  image_url for existing rows requires eBay API call per item - deferred.
EBAY_METADATA_FIX_PLAN.md = created / committed 6ca962d.
eBay metadata mapping fix = IMPLEMENTED / pending review / not committed.
  Scope: 4 lines in backend/sources/ebay.py (_ebay_item_to_raw + _normalize_candidate).
  New test file: backend/test_ebay_metadata_mapping.py (27 tests, stdlib unittest, no API calls).
  27 new tests pass. 51 decision engine regression tests pass. py_compile: all 5 files OK.
  No DB schema change. No db.py change. No decision_engine change. No frontend change.
  No discovery run. No DB data changed. No external APIs called.
  backend/.env not modified or printed. No secrets exposed.
  Fix applies to future discoveries only. Existing 37 eBay rows NOT backfilled.
  DB backfill remains separate pending owner approval.
YouTube setup is pending owner approval - not started.
CJ Phase 2/3 is not started.

**Owner must choose the next implementation step.**

Option A - Investigate eBay image_url pipeline gap (recommended first)
  Read backend/connectors/ebay.py and backend/db.py to confirm whether image_url is
  extracted and persisted by the eBay connector. Investigation only - no code change yet.
  71/76 products missing image_url. Fixing this is highest-ROI single action.
  No implementation starts without explicit owner approval.

Option B - Start CJ Phase 2 retail price enrichment
  5 CJ products all need retail_price (suggestSellPrice from GET /v1/product/query?pid=).
  All 5 have item_id. CJ token is active. Directly unblocks CJ Phase 3 shipping enrichment.
  Once approved: implement enrichment script, no DB schema change, no new connector.

Option C - Approve YouTube Data API setup
  Enable YouTube Data API v3 in GCP project, generate API key, implement YoutubeConnector.
  Lower ROI than A/B right now - does not resolve NEEDS_ENRICHMENT blockers.
  No implementation starts without explicit owner approval.

No action starts until one option is explicitly approved.
See DECISION_OUTPUT_AUDIT.md section 12-13 for ranked recommendation and rationale.

---

## Next allowed actions

1. **Monitor approval emails**  -  TikTok Developer Support + Google Trends alpha (see table above). All other connector work waits on these.
2. **Owner decision required**  -  choose Option A, B, or C above before any implementation begins.
   If Option B: Phase A is complete (FIELD_SCHEMA_REVIEW.md). Immediate next step = Phase B (backend/decision_engine.py, decide_product() pure function, no DB migration).
3. **CJ Phase 2** (when scheduled)  -  retail price enrichment via `GET /v1/product/query?pid=` per live product.
4. **CJ Phase 3** (when scheduled, after Phase 2)  -  shipping cost via CJ logistics endpoint.
5. **CJ token renewal**  -  run `refresh_cj_token.py` before 180-day expiry.
6. **eBay bug fixes only**  -  if a confirmed production bug surfaces.

---

## Blocked actions

- Do not implement Google Trends connector until alpha invitation received.
- Do not modify TikTok Ads until Developer Support responds.
- Do not use pytrends, web scraping, Google Ads, or BigQuery as Google Trends substitutes.
- Do not start Amazon, Keepa, AliExpress, or Reddit connectors.
- Do not implement Meta Ad Library  -  audit complete, implementation not approved.
- Do not implement YouTube Data API  -  setup not yet approved. Owner decision required before any connector code is written.
- Source expansion is allowed only as audit/research unless implementation is explicitly approved by the project owner.
- No automatic fallback connector. If pending approvals (TikTok, Google Trends) are delayed, the project owner must explicitly approve any new connector before implementation starts.
- Do not commit `backend/.env`  -  gitignored, contains live tokens.
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
| `CHECKPOINT_META_AD_LIBRARY_AUDIT.md` | Meta Ad Library official audit, coverage limitations, postpone decision |
| `CHECKPOINT_YOUTUBE_DATA_API_AUDIT.md` | YouTube Data API v3 official audit, quota model, signal types, proceed_to_setup decision |
| `SOURCE_STRATEGY_MAP.md` | Full source map: stage definitions, source categories, decision gates, data-to-decision mapping, near-term path |
| `PRODUCT_DECISION_ENGINE_PLAN.md` | Full decision engine design: lifecycle, decision statuses (TEST/WATCH/NEEDS_ENRICHMENT/REJECT), profitability model, hard rejection rules, confidence model, scoring components, reason system, next_action values, implementation phases A-G |
| `EXECUTION_BRIDGE_PLAN.md` | Code-level integration plan: maps decision engine design to actual repo files; Phase A field review and Phase B decide_product() integration; field mapping table; decision rules using existing fields only; API/export/frontend integration plan; test plan |
| `FIELD_SCHEMA_REVIEW.md` | Phase A complete: DB schema audit, _summary(row) field list (28 fields), scoring.py output review, normalize_candidate() persistence gaps, EXPORT_FIELDS current/proposed, decision engine field mapping table (55+ fields assessed), frontend field audit, 19-step Phase B checklist, non-available fields list |
| `MASTER_PROJECT_STATUS.md` | This file  -  cross-connector summary |
