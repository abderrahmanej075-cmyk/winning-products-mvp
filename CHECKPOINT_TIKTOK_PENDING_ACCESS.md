# CHECKPOINT: TikTok Ads — Pending API Access

Date: 2026-07-05

## Status: PENDING TIKTOK APPROVAL

TikTok Ads integration is blocked on TikTok granting API access.
No live calls are being made. No real data. Stub results only.

---

## Access request details

| Field | Value |
|---|---|
| Organization | Zaryotech |
| App name | Zaryotech Product Discovery |
| Requested API | TikTok Commercial Content API |
| Requested scope | research.adlib.basic |
| Endpoint needed | POST /v2/research/adlib/ad/query/ |
| Support ticket | Submitted 2026-07-05 |
| Expected response | 1–3 business days |

## Current blocker

The TikTok Developer Portal does not yet show:
- The **Commercial Content API** under Products
- The **research.adlib.basic** scope under Add Scopes

Support ticket submitted to TikTok Developer Support.
Awaiting portal access to become active.

---

## Current integration state

| Field | Value |
|---|---|
| provider | commercial_content_api |
| status | pending_access |
| data_mode | stub |
| can_fetch_real_data | false |
| live_call_confirmed | false |
| persisted | false |

`/health` → `tiktok_ads.status = pending_access`
`source_breakdown` → `tiktok_ads_stub` (not saved to DB)

---

## What to do when TikTok responds

**Step 1 — Confirm portal access:**
- Commercial Content API appears under Products
- research.adlib.basic scope is available under Add Scopes
- Add the scope to the app

**Step 2 — Obtain credentials:**
- Generate an access token with research.adlib.basic scope
- Note the base URL for the Commercial Content API

**Step 3 — Update `.env` (never share tokens):**
```
TIKTOK_API_PROVIDER=commercial_content_api
TIKTOK_API_TOKEN=<your_token>
TIKTOK_API_BASE_URL=https://open.tiktokapis.com
```

**Step 4 — Update connector for the official endpoint:**

The `_live_discover()` method in `backend/sources/tiktok_ads.py` currently
targets `GET /products/search` (third_party provider shape).
The Commercial Content API uses:
```
POST /v2/research/adlib/ad/query/
Content-Type: application/json
Authorization: Bearer {token}

{
  "filters": {
    "ad_published_date_range": {"min": "...", "max": "..."},
    "country_code": ["US"]
  },
  "search_field": "ad_title",
  "keyword": "posture corrector",
  "page": 1,
  "page_size": 10
}
```
A new `_commercial_content_api_discover()` method must be added before
connector can be marked live_configured or active.

**Step 5 — Restart backend, check health:**
Status should move from `pending_access` → `live_configured`

**Step 6 — Run verify endpoint:**
```
POST http://localhost:8000/sources/tiktok_ads/verify
{"seed": "posture corrector", "country": "US"}
```

**Step 7 — Confirm status auto-promotion:**
- `live_call_confirmed=true`
- `status=active` (automatic, no manual promotion)
- `source_breakdown={"tiktok_ads": N}`
- `db_save.inserted > 0`

---

## Completion criteria

TikTok Ads is complete when ALL of the following are confirmed:

- [ ] TikTok responds to support ticket
- [ ] Commercial Content API visible in portal
- [ ] research.adlib.basic scope visible and added to app
- [ ] TIKTOK_API_TOKEN set (access token with research.adlib.basic scope)
- [ ] `_commercial_content_api_discover()` implemented in tiktok_ads.py
- [ ] POST /sources/tiktok_ads/verify returns `live_call_confirmed=true`
- [ ] connector status = `active` (auto-promoted via flag file)
- [ ] source_breakdown shows `{"tiktok_ads": N}` (not `tiktok_ads_stub`)
- [ ] db_save.inserted > 0
- [ ] /products shows `source=tiktok_ads` products
- [ ] /export/products includes `tiktok_ads` products

---

## What is frozen while waiting

- eBay: live, complete, frozen — do not modify
- CJ Dropshipping: scaffold paused — do not continue until TikTok is complete
- Google Trends / Amazon / AliExpress / Reddit / YouTube / Meta: all paused

---

## No scraping. No access-rule bypass.

Official TikTok Commercial Content API only.
Authorization via `Authorization: Bearer {token}` header (never hardcoded).
research.adlib.basic scope only — no elevated permissions requested.
