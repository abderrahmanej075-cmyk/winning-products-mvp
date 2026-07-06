# CHECKPOINT: TikTok Ads API Status

Date: 2026-07-05

## Current status: NOT LIVE

TikTok Ads is a scaffold connector. It is not connected to any real data source.
No live calls will be made until a real provider is configured and verified.

## Why live is not available yet

The TikTok for Business API (`business-api.tiktok.com`) does NOT expose a product
search endpoint. It manages ad campaigns and creatives — not product browsing.

No official TikTok API provides a public product search endpoint suitable for
dropshipping product intelligence as of 2026-07-05.

The implemented live route (`GET {TIKTOK_API_BASE_URL}/products/search`) targets
third-party ad intelligence platforms (Minea, Pipiads, BigSpy, AdSpy, etc.)
that expose a REST product/ad search API. These are paid, compliant services.

## Current mode

| Field | Value |
|---|---|
| provider | placeholder (default) |
| status | stub_only |
| live_call_confirmed | false |
| can_fetch_real_data | false |
| data saved to DB | no |

## Stub data

5 curated stub products are returned with realistic signal values
(tiktok_hashtag_views, supplier_cost, retail_price, etc.).
Stub source name is `tiktok_ads_stub`.
Stub data is never saved to the database.
UI shows an orange warning banner and dashed stub card borders.

## Status progression (automatic, never manual)

```
stub_only        provider=placeholder or credentials missing
live_configured  provider + token + base_url all set, verify not yet run
live_untested    POST /sources/tiktok_ads/verify was run but call failed
active           POST /sources/tiktok_ads/verify succeeded — auto-promoted
```

Status becomes `active` automatically only when:
1. provider is configured (`third_party` or `mock`)
2. TIKTOK_API_TOKEN is set
3. TIKTOK_API_BASE_URL is set
4. POST /sources/tiktok_ads/verify succeeds (≥1 candidate returned)
5. Flag file `.tiktok_ads_live_confirmed.json` written with `live_call_confirmed=true`
6. /products shows `source=tiktok_ads` products
7. /export includes `tiktok_ads` products

## Required .env variables

```
# Choose a provider:
#   placeholder  → always stub (default, no live calls)
#   third_party  → paid ad-intelligence API (Minea, Pipiads, BigSpy, etc.)
#   mock         → local test server
TIKTOK_API_PROVIDER=

# Token for the configured provider (Bearer token / API key)
TIKTOK_API_TOKEN=

# Provider's base URL (e.g. https://api.pipiads.com)
TIKTOK_API_BASE_URL=

# true → API errors fall back to stub silently (recommended)
TIKTOK_FALLBACK_TO_STUB=true
```

## How to verify real data when credentials are available

1. Add to `backend/.env`:
   ```
   TIKTOK_API_PROVIDER=third_party
   TIKTOK_API_TOKEN=<your_provider_key>
   TIKTOK_API_BASE_URL=<provider_base_url>
   ```
2. Restart backend.
3. Check connector health — should show `status=live_configured`.
4. Run verification:
   ```
   POST http://localhost:8000/sources/tiktok_ads/verify
   {"seed": "posture corrector", "country": "US"}
   ```
5. Confirm response shows:
   - `live_call_success=true`
   - `live_call_confirmed=true`
   - `candidates_returned > 0`
   - `saved_to_db > 0`
6. Check connector health again — `status` should now be `active` automatically.
7. Run `/products` — should show `source=tiktok_ads` products.
8. Run `/export/products?filter=all` — should include `tiktok_ads` products.

## Completion criteria

TikTok Ads is complete when ALL of the following are true:
- [ ] provider=third_party or mock
- [ ] TIKTOK_API_TOKEN set
- [ ] TIKTOK_API_BASE_URL set
- [ ] POST /sources/tiktok_ads/verify returns live_call_confirmed=true
- [ ] connector status=active (auto-promoted, not manual)
- [ ] source_breakdown shows {"tiktok_ads": N} (not tiktok_ads_stub)
- [ ] db_save.inserted > 0
- [ ] /products shows tiktok_ads products
- [ ] /export/products includes tiktok_ads products

## Files introduced for this integration

| File | Purpose |
|---|---|
| backend/sources/tiktok_ads.py | Collector + stub + flag file helpers |
| backend/.tiktok_ads_live_confirmed.json | Runtime flag (gitignored) — written by verify endpoint |
| backend/sources/connectors/__init__.py | TikTokAdsConnector with 4-state status |
| backend/main.py | POST /sources/tiktok_ads/verify endpoint |
| backend/.env.example | TIKTOK_API_PROVIDER + TIKTOK_API_TOKEN + TIKTOK_API_BASE_URL |
| CHECKPOINT_TIKTOK_API_STATUS.md | This file |

## No scraping. No access-rule bypass.

Only compliant REST API calls via httpx. Bearer token in Authorization header.
Risk filter applied to all seeds and returned product titles.
