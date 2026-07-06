# CHECKPOINT: Google Trends — Pending Alpha Access

Date: 2026-07-06

## Current status: pending_access

| Field | Value |
|---|---|
| status | `pending_access` |
| application_submitted | `true` |
| submitted_at | `2026-07-06` |
| submitted_email | `admin@zaryotech.com` |
| google_cloud_project_id | `zaryotech-product-discovery` |
| project_name | `Zaryotech Product Discovery` |
| organization_type | `Private company` |
| use_case | `Commercial` |
| feedback_availability | `Both email and video conference` |
| official_api | `true` |
| unofficial_clients_allowed | `false` |
| pytrends_allowed | `false` |
| scraping_allowed | `false` |
| google_ads_substitute_allowed | `false` |
| bigquery_substitute_allowed | `false` — not an active path in this phase |
| live_call_confirmed | `false` |
| can_fetch_real_data | `false` |
| db_persistence | `none` |
| stub_products | `none` |
| next_action | Wait for Google approval email at admin@zaryotech.com |

---

## Application submission — 2026-07-06

Application submitted via the official form at:
**https://developers.google.com/search/apis/trends**

Confirmation received:
> "Thank you for your application! We'll notify you if you're accepted to Trends API alpha test."

---

## Official access audit — 2026-07-06

### Official API details

| Field | Value |
|---|---|
| Official API name | Google Trends API (alpha) |
| Announced | July 2025 (Google Search Central Blog) |
| Phase | Alpha — limited access, invitation only |
| Documentation access | Gated — requires alpha invitation; docs return 404 or require the invited email |
| Hosted at | `https://developers.google.com/search/apis/trends` |
| Application form | Same page: "Apply for the alpha" section |
| Operated by | Google Search Central |

### What the API provides (from public announcement)

| Capability | Detail |
|---|---|
| Data range | 5 years of rolling data |
| Aggregations | Daily, weekly, monthly, yearly |
| Geo filtering | Country + sub-region |
| Scaled comparisons | Compare dozens of terms (vs. 8-term limit in the web UI) |
| Signal type | Search interest (0-100 scale), trend direction |
| Consistent scaling | Historical data is not reprocessed — allows reliable time-series comparison |

### What is NOT publicly documented until approval

- Authentication method (OAuth 2.0 / API key / service account — not confirmed)
- Endpoint paths and request format
- Response schema and field names
- Rate limits and quotas
- Pricing (if any beyond free tier)
- SLA / data freshness guarantees

---

## Access rules for this phase

| Source / Substitute | Status |
|---|---|
| Google Trends API Alpha (official) | **Allowed — after invitation only** |
| pytrends | **NOT ALLOWED** — unofficial, undocumented client |
| Web scraping | **NOT ALLOWED** |
| Google Ads API as substitute | **NOT ALLOWED** |
| BigQuery public dataset | **NOT an active path in this phase** |
| Any unofficial implementation | **NOT ALLOWED** |

---

## Files changed for this checkpoint

| File | Change |
|---|---|
| `backend/sources/connectors/google_trends_official.py` | Status default: `disabled` → `pending_access`; `check()` updated with `official_api`, `requires_approval`, `access_pending`, `live_call_confirmed`, `data_type`, `alpha_program` block; application URL corrected; `GOOGLE_TRENDS_OFFICIAL_ENABLED` removed from required/missing env vars; BigQuery references removed from docstring and notes |
| `backend/.env.example` | Added Google Trends official API section (all commented out, pending_access state, no BigQuery lines) |
| `CHECKPOINT_GOOGLE_TRENDS_PENDING_ACCESS.md` | This file |

---

## Connector health snapshot (current state)

```
GET /sources/connectors/health → connectors.google_trends

status:              pending_access
implemented:         false
official_api:        true
requires_approval:   true
access_pending:      true
live_call_confirmed: false
can_fetch_real_data: false
data_type:           trend_signal
```

---

## Completion criteria

### Phase 1 — Apply (complete)
- [x] Application submitted at https://developers.google.com/search/apis/trends
- [x] Submitted email: admin@zaryotech.com
- [x] Google Cloud project: zaryotech-product-discovery
- [x] Confirmation received from Google

### Phase 2 — After approval
- [ ] Alpha invitation received at admin@zaryotech.com
- [ ] API docs accessible (login with admin@zaryotech.com)
- [ ] Authentication method confirmed from official docs
- [ ] Endpoint format and response schema documented
- [ ] Set `GOOGLE_TRENDS_OFFICIAL_ACCESS_MODE=confirmed` in `.env`
- [ ] Set `GOOGLE_CLOUD_PROJECT_ID=zaryotech-product-discovery` in `.env`
- [ ] Set `GOOGLE_APPLICATION_CREDENTIALS` in `.env`
- [ ] Run `POST /sources/google_trends/verify` — live call confirmed
- [ ] Status auto-promotes to `active`
- [ ] Connector implementation in `backend/sources/google_trends.py`

### Phase 3 — Integration (after Phase 2 complete)
- [ ] Multisource integration (signal enrichment, not DB product save)
- [ ] Scoring fields populated: `trends_interest`, `trends_direction_pct`, `seasonality_ratio`
- [ ] Frontend source option added

---

## Freeze rules

- eBay: live, complete, frozen — do not modify
- TikTok Ads: pending_access — do not touch until TikTok Developer Support responds
- CJ Dropshipping: CLOSED — active, live, frozen except Phase 2/3 enrichment
- **Google Trends: pending_access — do not implement until official alpha invitation received at admin@zaryotech.com**
- Amazon / AliExpress / Reddit / YouTube / Meta: paused
