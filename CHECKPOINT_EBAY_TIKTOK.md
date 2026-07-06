# MILESTONE: eBay live verified + TikTok Ads scaffold verified

Date: 2026-07-05

## Accepted source status

| source | mode | credentials | saves_to_db | dashboard_visible | connector_status |
|---|---|---|---|---|---|
| `ebay` | live (production) | eBay production keys set | yes | yes (33+ products) | ready |
| `tiktok_ads_stub` | stub | none required | no | no | stub_only |
| `manual` | live | none required | yes | yes | active |

## eBay verification result

- Environment: production
- production_calls_allowed: true
- can_fetch_real_data: true
- Fields saved to DB: source, source_url, score, recommendation, discovered_at
- Dedup: 3-tier (source+URL, source+item_id, source+normalized_name)

## TikTok Ads scaffold

- Connector: TikTokAdsConnector in sources/connectors/__init__.py
- Collector: sources/tiktok_ads.py (TikTokAdsCollector + _stub_response)
- Registry: status="active" for routing, connector status="stub_only" for health
- Health states: stub_available → live_untested → active (not yet reached)
- Stub data: 5 curated products with supplier_cost, social signals, margin data
- source_info.data_mode="stub" in response; persisted=false; not saved to DB
- UI: orange warning banner + dashed stub card when _stub source detected

## Files changed in this milestone

| File | Change |
|---|---|
| backend/main.py | TikTok dispatch, source_info field, live_sources update |
| backend/sources/tiktok_ads.py | New — TikTokAdsCollector + stub |
| backend/sources/connectors/__init__.py | TikTokAdsConnector with nuanced status |
| backend/sources/registry.py | tiktok_ads active entry |
| frontend/pages/index.js | TikTok Ads option, stub UI banner + card style |

## Security confirmation

- No .env contents printed or committed
- No API keys, tokens, or secrets in any file
- No credentials in git history

## Freeze note

eBay and TikTok Ads implementations are frozen. Do not modify unless a blocking bug appears.

## Next milestone

CJ Dropshipping — supplier cost signal source.
