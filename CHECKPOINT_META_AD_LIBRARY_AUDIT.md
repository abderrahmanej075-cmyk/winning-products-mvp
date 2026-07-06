# CHECKPOINT: Meta Ad Library API — Official Access Audit

Date: 2026-07-07
Status: audit_only / postponed / not_approved_for_implementation

---

## Audit summary

| Field | Value |
|---|---|
| Official API name | Meta Ad Library API |
| Graph API reference node | `ads_archive` |
| Endpoint | `GET https://graph.facebook.com/<VERSION>/ads_archive` |
| Current version | v25.0 |
| Operated by | Meta for Developers |
| Primary documentation | `https://developers.facebook.com/docs/graph-api/reference/ads_archive/` |
| Field reference | `https://developers.facebook.com/docs/graph-api/reference/archived-ad/` |

---

## Access requirements

| Requirement | Required | Notes |
|---|---|---|
| Facebook / Meta account | **yes** | mandatory starting point |
| Identity + location confirmation | **yes** | via facebook.com/ID — process to run ads about social issues, elections, or politics. Can take several days. Required before app approval. |
| Meta for Developers account | **yes** | sign up at developers.facebook.com; agree to Platform Policy |
| Meta Developer app | **yes** | must be created in Meta developer dashboard |
| OAuth 2.0 access token | **yes** | user token with appropriate permissions; attached to the developer app |
| Business verification | no (for basic read) | may be required for higher access tiers |
| Ads Manager account | no | this is read-only archive access, not campaign management |

---

## What data the API returns

### Available for ALL ad types (including product / ecommerce ads)

| Field | Description |
|---|---|
| `ad_creative_bodies` | Ad copy / body text |
| `ad_creative_link_captions` | Link caption (often domain or CTA) |
| `ad_creative_link_descriptions` | Link description text |
| `ad_creative_link_titles` | Link headline |
| `ad_creation_time` | When the ad was created |
| `ad_delivery_start_time` | When delivery began |
| `ad_delivery_stop_time` | When delivery ended (if stopped) |
| `page_id` | Advertiser Facebook page ID |
| `page_name` | Advertiser Facebook page name |
| `ad_snapshot_url` | Visual snapshot of ad creative (images + videos) |
| `publisher_platforms` | facebook, instagram, audience_network, messenger |
| `languages` | Language(s) the ad ran in |

### Restricted — political / issue ads only (NOT available for product ads)

| Field | Notes |
|---|---|
| `spend` | Reported in ranges (e.g. "$500–$999") |
| `impressions` | Reported in ranges |
| `estimated_audience_size` | Estimated reach |
| `eu_total_reach` | EU-specific reach |
| `demographic_distribution` | Age + gender breakdown |
| `delivery_by_region` | Geographic delivery split |
| `target_ages`, `target_gender`, `target_locations` | Targeting details |
| `bylines`, `beneficiary_payers` | Funding disclosure |

**For non-political product ads: no spend data, no impressions, no targeting, no reach metrics are returned.**

---

## Coverage limitations — critical

### Ad type coverage

| ad_type value | What it covers |
|---|---|
| `ALL` (default) | All ad types — but subject to the EU geographic restriction below |
| `POLITICAL_AND_ISSUE_ADS` | Social issues, elections, politics — global |
| `EMPLOYMENT_ADS` | Employment ads — global |
| `HOUSING_ADS` | Housing ads — global |
| `FINANCIAL_PRODUCTS_AND_SERVICES_ADS` | Financial products — global |

There is no `ECOMMERCE_ADS` or `PRODUCT_ADS` type. Product / DTC / dropshipping ads fall under the default `ALL` query.

### The EU geographic restriction

> "Ads that did not reach any location in the EU will only return if they are about social issues, elections or politics."

**Implication for dropshipping product discovery:**
- Ads that ran **only in the US** (or AU, CA, etc.) and never reached an EU country → **invisible via the API**
- Ads that ran **globally or EU-inclusive** → accessible via the API
- Many US-focused DTC brands run US-only ad sets → their ads will not appear
- Dropshipping stores targeting only the US market may be entirely absent

This is the primary limitation for using Meta Ad Library as a product discovery signal.

### Batch download restriction

> "You cannot currently download a batch of archived ads."

Individual ad creatives can be analyzed; bulk export is not supported.

---

## Marketing API — clarification

The **Meta Marketing API** is for managing **your own** ad campaigns:
- create/update/delete campaigns, ad sets, ads
- access your own performance metrics (spend, CPC, ROAS, conversions)
- manage budgets and audiences

It has **no competitor / product discovery capability**. It is irrelevant to this project's discovery goal and should not be confused with the Ad Library API.

---

## Suitability for dropshipping product discovery

| Capability | Available | Notes |
|---|---|---|
| Keyword search for product ads | **yes** | `search_terms` param, up to 100 chars |
| Filter by country | **yes** | `ad_reached_countries` — but EU restriction applies |
| See ad creative (copy, headline, description) | **yes** | useful for spotting product angles |
| See ad visual (image / video snapshot) | **yes** | via `ad_snapshot_url` |
| Identify active advertisers (page name + page ID) | **yes** | can track specific brands |
| Filter by active vs inactive | **yes** | `ad_active_status` param |
| See spend / budget for product ads | **no** | political ads only |
| See impressions / reach for product ads | **no** | political ads only |
| Rank ads by performance | **no** | no performance data available |
| US-only ad coverage | **limited** | EU restriction means many US-focused stores invisible |
| Batch export | **no** | individual retrieval only |

### Signal usefulness rating

**Partial signal, not a primary discovery source.**

- Useful for: finding what products/categories are actively being advertised on Meta+Instagram; reading ad copy angles; identifying brand page names for further research.
- Not useful for: ranking winning products by ad spend or impressions; discovering US-only dropshipping ads; confirming a product is a "winner" vs. a one-time test.
- Without spend/impressions, all visible ads look equal — a test ad with $5 spend and a $50,000/month winner are indistinguishable via API.

**Conclusion: conditionally useful as a secondary creative/trend signal, not suitable as a primary product scoring source.**

---

## Proposed status model (if we proceed)

```
connector name:          meta_ads_library
status:                  pending_setup
official_api:            true
live_call_confirmed:     false
can_fetch_real_data:     false   (until token + verify endpoint confirmed)
db_persistence:          none    (signal-only source — no stub/fake ads ever saved)
unofficial_clients:      false
scraping:                false
```

Status progression:
```
pending_setup       default — app not created, no token
missing_credentials app created but token absent
ready               token set + live verify call confirmed
```

---

## Exact setup steps (if owner approves proceeding)

1. **Facebook account** — confirm an existing FB account is available for Zaryotech.
2. **Identity confirmation** — go to `https://www.facebook.com/ID`, complete identity + location confirmation. Allow several days for Meta to process.
3. **Meta Developer account** — visit `https://developers.facebook.com`, select "Get started", agree to Platform Policy.
4. **Create app** — in the Meta Developer dashboard, create a new app. App type: "Other" or "Consumer". Add "Ad Library API" product.
5. **Request access token** — generate a User Access Token with `ads_read` permission (or use the App Token for public Ad Library searches — confirm which is required for `ads_archive`).
6. **Set in `.env`**: `META_AD_LIBRARY_TOKEN=<token>` (gitignored, never committed).
7. **Run verify endpoint** — `POST /sources/meta_ads_library/verify` → confirm live call returns results → auto-promote to `active`.

---

## Access rules for this connector

| Source | Status |
|---|---|
| Meta Ad Library API (official) | Allowed — after setup |
| Meta Marketing API for competitor discovery | NOT applicable — own-ads management only |
| Scraping facebook.com/ads/library | NOT ALLOWED |
| Browser automation / Selenium | NOT ALLOWED |
| Third-party ad spy tools (Minea, BigSpy, Pipiads) | NOT approved in this phase |
| Any unofficial Meta API client | NOT ALLOWED |

---

## Recommendation

**Postpone — not approved as the next connector.**

**Final decision:**
- Meta Ad Library API is official but limited for dropshipping product discovery.
- It may be useful later as a secondary creative-angle signal (ad copy, headlines, image snapshots for EU-reachable ads).
- It is not suitable as the next primary source: no spend data, no impressions for product ads, EU geographic restriction hides US-only advertisers.
- No implementation is approved now.
- YouTube Data API should be audited next as the more suitable official signal source.

**Connector fallback rule:**
No fallback connector is approved automatically. If TikTok and Google approvals are delayed, the project owner must explicitly approve any new connector before implementation starts.

Reasons for postponing Meta:
- EU coverage restriction significantly limits US-focused product discovery
- No spend / impressions data for product ads — can't rank winners
- Requires Facebook identity confirmation + developer app creation (~days of setup)
- Signal quality is lower than TikTok (engagement data) or Google Trends (search volume)
- YouTube Data API offers search-volume-adjacent signals with no approval queue and no geographic blind spots of this kind

---

## Files changed

| File | Change |
|---|---|
| `CHECKPOINT_META_AD_LIBRARY_AUDIT.md` | This file — created |

No connector logic changed. No `.env` modified. No commit yet.

---

## Freeze rules (unchanged)

| Connector | Rule |
|---|---|
| eBay | FROZEN — live, complete |
| CJ Dropshipping | CLOSED — frozen except Phase 2/3 enrichment |
| TikTok Ads | FROZEN — waiting for TikTok Developer Support |
| Google Trends | FROZEN — waiting for alpha invitation at admin@zaryotech.com |
| Meta Ad Library | **postponed** — not approved for implementation; audit complete |
