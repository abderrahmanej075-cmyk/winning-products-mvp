# Field Schema Review

Phase: A (documentation only)
Last updated: 2026-07-07
Status: review_complete / no_code_implemented / no_db_changed

---

## 1. Executive summary

This is Phase A of the Product Decision Engine implementation.

No code was implemented. No DB schema changed. No API calls made.
No connector logic modified. No backend/.env read or modified.

Purpose: verify which fields are available in the actual codebase so that
backend/decision_engine.py (Phase B) can be written using only confirmed fields.

Phase B must only use fields confirmed as available in this document.

Key findings:

Finding 1: decide_product() can receive the _summary(row) dict directly.
  All fields needed for Phase B decision rules are present in _summary(row)
  output, with explicit None values for missing data.
  No new DB columns are required for Phase B.

Finding 2: scoring confidence is almost always "Low" for current live data.
  scoring.py computes confidence across 19 fields (CONFIDENCE_FIELDS).
  Live CJ + eBay products populate at most 3 of those 19 fields:
  supplier_cost (CJ), product_weight_kg (CJ), retail_price (eBay only).
  Because 3/19 = 15.8%, scoring confidence = "Low" for virtually all
  current live products. Phase B correctly produces NEEDS_ENRICHMENT and WATCH
  for these products, not TEST. This is expected and useful behavior.

Finding 3: normalize_candidate() output is NOT fully persisted.
  upsert_discovered_candidate() (db.py:436) inserts only 15 fields.
  Fields like missing_data, risk_flags, demand_signal, margin_signal, and
  evidence that normalize_candidate() produces are NOT stored in the DB.
  Phase B cannot rely on these fields from DB records.
  All such signals are re-computed at query time by score_product() inside
  _summary(row). Phase B should consume re-computed outputs, not persisted ones.

Finding 4: /products/{pid} uses a different response shape from /products.
  /products and /export/products use _summary(row).
  /products/{pid} returns {"product": <raw row dict>, "scoring": score_product(p)}.
  The frontend detail drawer reads scoring.confidence as the full dict
  ({level, supported, denominator, percent}) via the "scoring" key.
  The frontend list reads p.confidence as a plain string via the "product/list" key.
  Phase B must preserve both representations.

Finding 5: EXPORT_FIELDS is a plain list, additively extendable.
  Adding decision fields to EXPORT_FIELDS (main.py:2749) requires one line change.
  No client-breaking changes result from appending new field names.

---

## 2. Actual DB schema review

Source: backend/db.py

### products table base columns (CREATE TABLE, db.py:82)

| Column | SQLite type | Notes |
|---|---|---|
| id | INTEGER PRIMARY KEY AUTOINCREMENT | row id |
| name | TEXT NOT NULL | product title |
| category | TEXT | product category |
| country | TEXT DEFAULT 'US' | target market |
| created_at | TEXT | ISO 8601 datetime |
| trends_interest | INTEGER | Google Trends 0-100 |
| amazon_bsr | INTEGER | Amazon Best Seller Rank |
| reddit_posts_90d | INTEGER | Reddit post count |
| pinterest_saves | INTEGER | Pinterest save count |
| trends_direction_pct | REAL | Trend direction % |
| seasonality_ratio | REAL | Seasonal ratio |
| tiktok_momentum | TEXT | "trending" / "surging" / etc. |
| supplier_cost | REAL | CJ sellPrice = dropshipper cost |
| shipping_cost | REAL | confirmed logistics cost |
| retail_price | REAL | market benchmark price |
| product_weight_kg | REAL | CJ productWeight / 1000 |
| tiktok_hashtag_views | INTEGER | TikTok hashtag view count |
| meta_active_advertisers | INTEGER | Meta active advertiser count |
| meta_ad_longevity_days | INTEGER | Meta ad longevity |
| demo_videos_top10 | INTEGER | demo video count (top 10) |
| aliexpress_sellers_1k | INTEGER | AliExpress sellers (thousands) |
| brand_dominance_pct | REAL | brand dominance % |
| competitor_count | INTEGER | competitor count |
| diff_unaddressed_themes | INTEGER | unaddressed review themes |
| diff_complement_skus | INTEGER | complement SKU count |
| diff_oem_available | INTEGER | OEM available (bool as int) |
| diff_market_fragmented | INTEGER | market fragmented (bool as int) |
| diff_organic_ugc | INTEGER | organic UGC count |
| legal_restricted | INTEGER | legal restriction flag (bool as int) |
| hazmat | INTEGER | hazmat flag (bool as int) |
| fragile_material | INTEGER | fragile material flag (bool as int) |
| breakage_mentions | INTEGER | breakage mention count |
| longest_dim_cm | REAL | longest dimension in cm |
| seasonality_offpeak | INTEGER | currently off-peak (bool as int) |
| alltime_current_value | INTEGER | all-time Trends current value |

### Migrated columns (ALTER TABLE, db.py:123)

| Column | Notes |
|---|---|
| source | source connector name (e.g. "ebay", "cj_dropshipping") |
| source_url | direct link to original listing (may be None) |
| item_id | source item ID (eBay item ID or CJ pid) |
| image_url | product image URL (from CJ productImage) |
| score | scoring.py computed score (/60, may be None if eliminated) |
| recommendation | scoring.py recommendation string |
| discovered_at | ISO 8601 datetime of first discovery |
| shortlisted | INTEGER DEFAULT 0 (bool as int) |
| shortlisted_at | TEXT, ISO 8601 datetime |
| review_status | TEXT DEFAULT 'new' (new/researching/test_candidate/rejected/winner) |
| operator_notes | TEXT, free-form notes from operator |
| reviewed_at | TEXT, ISO 8601 datetime |

### ALLCOLS (db.py:15)

ALLCOLS is the list of columns accepted by insert_product().
It does NOT include the migrated columns. upsert_discovered_candidate()
uses its own explicit INSERT statement (db.py:436) which covers:
  name, category, country, source, source_url, item_id, image_url,
  retail_price, supplier_cost, shipping_cost, product_weight_kg,
  score, recommendation, discovered_at, created_at

### Fields in DB but NOT currently returned by _summary(row)

The following DB columns exist and can be read from the raw row but are NOT
included in the _summary(row) return dict (main.py:160). They are available
via db.fetch_by_id() but not via the /products list endpoint.

| DB column | In DB? | In _summary? | Notes |
|---|---|---|---|
| trends_interest | yes | no | scoring input field |
| amazon_bsr | yes | no | scoring input field |
| reddit_posts_90d | yes | no | scoring input field |
| pinterest_saves | yes | no | scoring input field |
| trends_direction_pct | yes | no | scoring input field |
| seasonality_ratio | yes | no | scoring input field |
| tiktok_momentum | yes | no | scoring input field |
| tiktok_hashtag_views | yes | no | scoring input field |
| meta_active_advertisers | yes | no | scoring input field |
| meta_ad_longevity_days | yes | no | scoring input field |
| demo_videos_top10 | yes | no | scoring input field |
| aliexpress_sellers_1k | yes | no | scoring input field |
| brand_dominance_pct | yes | no | scoring input field |
| competitor_count | yes | no | scoring input field |
| diff_unaddressed_themes | yes | no | scoring input field |
| diff_complement_skus | yes | no | scoring input field |
| diff_oem_available | yes | no | scoring input field |
| diff_market_fragmented | yes | no | scoring input field |
| diff_organic_ugc | yes | no | scoring input field |
| legal_restricted | yes | no | filter input (drives filter_reasons via scoring) |
| hazmat | yes | no | filter input |
| fragile_material | yes | no | filter input |
| breakage_mentions | yes | no | filter input |
| longest_dim_cm | yes | no | filter input |
| seasonality_offpeak | yes | no | filter input |
| alltime_current_value | yes | no | filter input |

These fields are used by score_product() (called inside _summary()), so their
effects flow into _summary output as scoring outputs (filter_reasons, cautions,
score, recommendation, etc.). Phase B does not need them directly.

### Fields that do NOT exist in DB at all

| Field | Status | Notes |
|---|---|---|
| ebay_avg_price | not in DB | defined in PRODUCT_DECISION_ENGINE_PLAN.md as future field |
| ebay_median_price | not in DB | same |
| ebay_listing_count | not in DB | same |
| ebay_benchmark_confidence | not in DB | same |
| matching_confidence | not in DB | same |
| supplier_availability | not in DB | approximated by supplier_cost presence |
| cj_vid | not in DB | needed for Phase 3 shipping; item_id = cj_pid only |
| restricted_category_risk | not in DB | approximated by legal_restricted + filter_reasons |
| branded_counterfeit_risk | not in DB | approximated by filter_reasons F1 detection |
| medical_claims_risk | not in DB | not detected by current scoring |
| battery_risk | not in DB | approximated by hazmat flag |
| fragile_risk | not in DB | approximated by fragile_material flag |

Phase B cannot use any of these. They are documented here to confirm they must
not appear in decide_product() logic without being added first.

---

## 3. _summary(row) output review

Source: backend/main.py, function _summary(row, cac=None), lines 160-192.

### Exact fields returned by _summary(row)

| Field key | Source | Type | Notes |
|---|---|---|---|
| "id" | DB row | int | primary key |
| "name" | DB row | str | product title |
| "category" | DB row | str or None | product category |
| "country" | DB row | str or None | target market |
| "source" | DB row | str or None | connector name |
| "item_id" | DB row | str or None | source item ID |
| "source_url" | DB row | str or None | link to original listing |
| "image_url" | DB row | str or None | product image URL |
| "discovered_at" | DB row | str or None | ISO datetime |
| "retail_price" | DB row | float or None | market benchmark price |
| "supplier_cost" | DB row | float or None | CJ cost per unit |
| "shipping_cost" | DB row | float or None | confirmed logistics cost |
| "product_weight_kg" | DB row | float or None | product weight |
| "shortlisted" | DB row | bool | converted from int (0/1) |
| "shortlisted_at" | DB row | str or None | ISO datetime |
| "review_status" | DB row | str | defaults to "new" if null |
| "operator_notes" | DB row | str or None | free text |
| "reviewed_at" | DB row | str or None | ISO datetime |
| "score" | scoring.py | float or None | /60; None if eliminated |
| "score_max" | constant | int | always 60 |
| "recommendation" | scoring.py | str | "Reject" / "Watchlist" / "Test with small budget" / "Strong candidate" |
| "confidence" | scoring.py | str | "High" / "Medium" / "Low" (level only, not full dict) |
| "net_profit_per_order" | scoring.py | float or None | None if any of retail/cost/ship is missing |
| "eliminated" | scoring.py | bool | True if any F1-F8 filter triggered |
| "positive_reasons" | scoring.py | list of str | [] when no positive signals |
| "caution_reasons" | scoring.py | list of str | [] when no cautions; may contain filter cautions |
| "filter_reasons" | scoring.py | list of str | [] when not eliminated; non-empty = eliminated |
| "score_breakdown" | scoring.py | dict | {category: {score, max}} per scoring category |

### CRITICAL: confidence is a string in _summary, not a dict

_summary(row) returns "confidence" as a plain string: "High", "Medium", or "Low".
Source: main.py line 185: `"confidence": res["confidence"]["level"]`

The full confidence dict ({level, supported, denominator, percent}) is only
available from score_product() directly, NOT from _summary(row).

The frontend detail drawer (index.js:871) reads scoring.confidence.level from
the "scoring" key of /products/{pid} (which calls score_product() directly).
The frontend list view (index.js:664) reads p.confidence as a plain string from
the "product" items in /products.

Phase B consequence: decide_product() receives confidence as a string.
Map "High" -> "HIGH", "Medium" -> "MEDIUM", "Low" -> "LOW" for decision_confidence.

### API endpoint mapping

| Endpoint | Uses _summary? | Notes |
|---|---|---|
| GET /products (line 364) | YES | returns [_summary(r) for r in db.fetch_all()] |
| GET /export/products (line 2766-2779) | YES | calls _summary(row) per row, picks EXPORT_FIELDS |
| GET /products/{pid} (line 369-375) | NO | returns {"product": dict(row), "scoring": score_product(p)} |
| POST /products/score (line 404) | NO | calls score_product() directly |
| POST /discovery/manual | YES (via response layer) | returns score_product() output + product |
| POST /discovery/multisource | NO direct call | calls normalize_candidate() + score_product() |

Phase B integration points:
  - Replace _summary(row) calls in /products and /export/products with
    _summary_with_decision(row) wrapper.
  - /products/{pid}: optionally add _summary_with_decision for the "product"
    key. The "scoring" key stays as score_product() output, unchanged.
    This is a Phase B option, not a requirement.

---

## 4. scoring.py output review

Source: backend/scoring.py, function score_product(p, cac=DEFAULT_CAC), lines 327-390.

### Useful outputs for Phase B (via _summary(row))

| Output key | Type | Notes |
|---|---|---|
| "eliminated" | bool | True if any hard filter triggered |
| "filter_reasons" | list of str | F1-F8 hard filter reasons; non-empty means eliminated |
| "cautions" | list of str | C1 and risk overlay cautions (same as caution_reasons) |
| "caution_reasons" | list of str | alias of cautions (both present in output) |
| "positive_reasons" | list of str | positive signals found |
| "confidence" | dict | {level, supported, denominator, percent} — NOT the string |
| "net_profit_per_order" | float or None | retail - supplier_cost - shipping - cac |
| "score" | float or None | /60 adjusted; None if eliminated |
| "score_max" | int | always 60 |
| "score_breakdown" | dict | per-category {score: float, max: int} |
| "recommendation" | str | final verdict string |
| "recommendation_reason" | str | explanation string |
| "base_verdict" | str | pre-cap verdict |
| "categories" | dict | per-category {earned, measured_max, display, fields} |
| "cac_used" | float | CAC value used (default 20.0) |

### What _summary exposes vs what score_product returns

_summary(row) exposes only a subset of score_product() outputs.
Fields available in _summary but NOT as a full object:

- `confidence` in _summary is a string ("High"/"Medium"/"Low")
  In score_product() it is the full dict {"level", "supported", "denominator", "percent"}.

- `score_breakdown` in _summary is the simplified {category: {score, max}} dict.
  In score_product() `categories` contains the full per-category {earned, measured_max, display, fields}.

- `recommendation_reason`, `base_verdict`, `cac_used`, `categories` (full) are
  in score_product() output but NOT exposed by _summary(row).
  The frontend reads these from the "scoring" key of /products/{pid}.

### Hard filter reasons (run_filters output, scoring.py:153)

The following hard filter conditions produce entries in filter_reasons.
Phase B reads filter_reasons to confirm REJECT conditions.

  F1 legal: restricted/prohibited class    (from legal_restricted field)
  F1 cosmetic: FDA labeling caution        (from category == "cosmetics")
  F2 shipping: weight > 2kg               (from product_weight_kg > 2.0)
  F2 shipping: longest dimension > 60cm   (from longest_dim_cm > 60)
  F2 shipping: hazmat                      (from hazmat field)
  F2 shipping: ship cost > 30% of retail  (from shipping_cost / retail_price)
  F3 fragility: fragile material + breakage reports
  F4 seasonality: strongly seasonal and off-peak
  F5 market fit: no US demand signal
  F6 fad-collapse: historical peak >= 5x current and declining
  F7 digital: intangible/non-shippable product
  F8 margin: negative gross margin (price < cost + shipping)

Caution flags (C1 and others) are in caution_reasons and do NOT set eliminated=True.
They cap the recommendation at "Watchlist" but are not hard rejects.

### scoring.py CONFIDENCE_FIELDS (19 fields)

The 19 fields that determine the scoring confidence level:

  trends_interest, amazon_bsr, reddit_posts_90d, pinterest_saves,
  trends_direction_pct, seasonality_ratio, tiktok_momentum,
  retail_price, supplier_cost, shipping_cost, product_weight_kg,
  tiktok_hashtag_views, meta_active_advertisers, meta_ad_longevity_days,
  aliexpress_sellers_1k, brand_dominance_pct, competitor_count,
  diff_complement_skus, diff_oem_available

Threshold: >= 80% -> "High", >= 50% -> "Medium", else "Low"

### Confidence level for current live data

Live CJ products populate at most:
  supplier_cost (1), product_weight_kg (2)
  = 2 of 19 fields = 10.5% -> "Low" always

Live eBay products populate at most:
  retail_price (1)
  = 1 of 19 fields = 5.3% -> "Low" always

Products in DB from CJ discovery with eBay benchmark at retail_price:
  retail_price (1), supplier_cost (2), product_weight_kg (3)
  = 3 of 19 fields = 15.8% -> "Low" always

CONCLUSION: scoring confidence will be "Low" for all current live products.
Phase B produces NEEDS_ENRICHMENT and WATCH correctly. For current live CJ/eBay
records, TEST is expected to be rare or unreachable because scoring confidence is
usually Low and critical fields such as retail_price, supplier_cost, or shipping_cost
are often missing. CJ Phase 2/3 may improve margin completeness, but may not by itself
raise scoring confidence above Medium unless enough scoring confidence fields are
populated. This is correct behavior, not a bug. Products manually entered with all
required fields may still reach TEST if all Phase B conditions are met.

### What Phase B must not do

Phase B must NOT re-implement scoring logic in decision_engine.py.
All filter detection, confidence calculation, and margin computation
is already done by score_product() and exposed via _summary(row).
decide_product() reads results; it does not reproduce the computation.

---

## 5. normalize_candidate() output review

Source: backend/sources/normalize.py, function normalize_candidate(), lines 107-170.

### Full output of normalize_candidate()

| Field | Type | Notes |
|---|---|---|
| "name" | str | cleaned product title |
| "category" | str | category or "other" |
| "query" | str | search query that produced this result |
| "source" | str | connector name |
| "source_url" | str or None | |
| "item_id" | str or None | |
| "image_url" | str or None | |
| "retail_price" | float or None | |
| "shipping_cost" | float or None | |
| "supplier_cost" | float or None | |
| "product_weight_kg" | float or None | |
| "estimated_margin" | float or None | retail - supplier_cost - (shipping or 0); None if retail or cost missing |
| "score" | float or None | from score_result |
| "recommendation" | str or None | from score_result |
| "positive_reasons" | list | from score_result |
| "caution_reasons" | list | from score_result |
| "filter_reasons" | list | from score_result |
| "demand_signal" | str | "strong" / "moderate" / "weak" / "missing" |
| "trend_signal" | str | "strong" / "moderate" / "weak" / "missing" |
| "competition_signal" | str | "favorable" / "moderate" / "saturated" / "missing" |
| "social_signal" | str | "strong" / "moderate" / "weak" / "missing" |
| "supplier_signal" | str | "strong" / "moderate" / "weak" / "unconfirmed" / "missing" |
| "margin_signal" | str | "strong" / "moderate" / "weak" / "negative" / "missing" / "unconfirmed" |
| "risk_flags" | list | from score_result cautions |
| "missing_data" | list | fields from _SIGNAL_FIELDS that are None |
| "evidence" | dict | subset of raw numeric fields that are not None |

### What upsert_discovered_candidate() persists (db.py:436)

upsert_discovered_candidate() runs an explicit INSERT with 15 fields:
  name, category, country, source, source_url, item_id, image_url,
  retail_price, supplier_cost, shipping_cost, product_weight_kg,
  score, recommendation, discovered_at, created_at

### Fields produced by normalize_candidate() that are NOT persisted to DB

| Field | Persisted? | Reason / Phase B consequence |
|---|---|---|
| "query" | NO | search-time context only |
| "estimated_margin" | NO | re-computed at query time by scoring.compute_net() |
| "positive_reasons" | NO | re-computed by score_product() inside _summary() |
| "caution_reasons" | NO | re-computed by score_product() inside _summary() |
| "filter_reasons" | NO | re-computed by score_product() inside _summary() |
| "demand_signal" | NO | re-computed if needed; not in DB |
| "trend_signal" | NO | re-computed if needed; not in DB |
| "competition_signal" | NO | re-computed if needed; not in DB |
| "social_signal" | NO | re-computed if needed; not in DB |
| "supplier_signal" | NO | re-computed if needed; not in DB |
| "margin_signal" | NO | re-computed if needed; not in DB |
| "risk_flags" | NO | re-computed from score_result.cautions in _summary() |
| "missing_data" | NO | re-computed by normalize_candidate(); not in DB |
| "evidence" | NO | raw evidence snapshot; not in DB |

### Phase B consequence

Phase B cannot read normalize_candidate() outputs from the DB.
For any given product row, re-computation of these signals happens at query time
via score_product() inside _summary(row).

The "missing_data" list in decide_product() output is computed by the
decision engine itself from the _summary(row) dict fields, NOT read from a
persisted normalize_candidate() missing_data field.

The "risk_flags" list in decide_product() output is derived from:
  filter_reasons (hard filters) and caution_reasons (soft cautions)
already present in _summary(row). Not from a persisted normalize field.

---

## 6. EXPORT_FIELDS review

Source: backend/main.py, EXPORT_FIELDS constant, lines 2749-2755.

### Current EXPORT_FIELDS

  "id", "name", "category", "country", "source", "item_id", "source_url",
  "image_url", "retail_price", "supplier_cost", "shipping_cost",
  "product_weight_kg", "score", "recommendation",
  "shortlisted", "shortlisted_at",
  "review_status", "operator_notes", "reviewed_at", "discovered_at"

### Export mechanism (main.py:2776-2779)

  for row in rows:
      s = _summary(row)
      if fn(s):
          results.append({f: s.get(f) for f in EXPORT_FIELDS})

After Phase B wraps _summary with _summary_with_decision, s will contain
all decision fields. The export picks only fields in EXPORT_FIELDS.
No new decision fields will appear in export until EXPORT_FIELDS is extended.

### Proposed Phase B additions to EXPORT_FIELDS

  "decision", "decision_confidence", "margin_status", "estimated_net_margin",
  "missing_data", "risk_flags", "decision_reasons", "next_action"

Adding these to EXPORT_FIELDS is additive. The list fields (missing_data,
risk_flags, decision_reasons) serialize as their Python repr in CSV
(e.g., "['field1', 'field2']"). If cleaner CSV is desired, JSON-encode these
fields in a Phase B post-processing step. Not a blocker.

### Backward compatibility

Existing JSON export clients: all existing fields remain at same positions
in the product object. New keys are appended to each product dict.
Existing CSV export clients: existing columns remain in the same order.
New columns appear to the right of the last existing column.
No client-breaking changes result from extending EXPORT_FIELDS.

---

## 7. Decision Engine required fields mapping

### Master field mapping table

For each field the decision engine needs, this table shows its Phase B availability.

| Decision field | Required for Phase B? | In DB | In _summary | In scoring output | In normalize output | Phase B usable | Fallback / notes |
|---|---|---|---|---|---|---|---|
| name | YES | yes | yes (str) | no | yes | YES | never None (DB NOT NULL) |
| category | YES | yes | yes (str or None) | no | yes | YES | default "other" if None |
| country | optional | yes | yes (str or None) | no | yes | YES | default "US" if None |
| source | YES | yes (migrated) | yes (str or None) | no | yes | YES | None for manual entries |
| source_url | optional | yes (migrated) | yes (str or None) | no | yes | YES | commonly None for CJ/eBay |
| item_id | optional | yes (migrated) | yes (str or None) | no | yes | YES | use as cj_pid reference |
| image_url | YES (for TEST cap) | yes (migrated) | yes (str or None) | no | yes | YES | None blocks TEST |
| retail_price | YES | yes | yes (float or None) | no | yes | YES | None -> NEEDS_ENRICHMENT |
| supplier_cost | YES | yes | yes (float or None) | no | yes | YES | None -> NEEDS_ENRICHMENT or REJECT |
| shipping_cost | YES | yes | yes (float or None) | no | yes | YES | None -> NEEDS_ENRICHMENT (see cap) |
| product_weight_kg | YES | yes | yes (float or None) | no | yes | YES | None affects shipping estimate logic |
| score | secondary | yes (migrated) | yes (float or None) | yes | yes | YES | None if eliminated |
| recommendation | secondary | yes (migrated) | yes (str) | yes | yes | YES | always present |
| confidence | YES (as string) | no | yes ("High"/"Medium"/"Low") | yes (in full dict) | no | YES | always present; map to HIGH/MEDIUM/LOW |
| net_profit_per_order | YES | no | yes (float or None) | yes | no | YES | None if any of retail/cost/ship missing |
| eliminated | YES | no | yes (bool) | yes | no | YES | always present |
| positive_reasons | YES | no | yes (list) | yes | yes (via score_result) | YES | [] when empty |
| caution_reasons | YES | no | yes (list) | yes | yes (via score_result) | YES | [] when empty |
| filter_reasons | YES | no | yes (list) | yes | yes (via score_result) | YES | [] when not eliminated |
| score_breakdown | optional | no | yes (dict) | yes | no | YES | {} if eliminated |
| shortlisted | optional | yes (migrated) | yes (bool) | no | no | YES | always present |
| review_status | optional | yes (migrated) | yes (str) | no | no | YES | defaults to "new" |
| operator_notes | optional | yes (migrated) | yes (str or None) | no | no | YES | may be None |
| discovered_at | optional | yes (migrated) | yes (str or None) | no | no | YES | |
| ebay_avg_price | NO (Phase D) | no | no | no | no | NOT YET | future field; not available Phase B |
| ebay_median_price | NO (Phase D) | no | no | no | no | NOT YET | future field; not available Phase B |
| ebay_benchmark_confidence | NO (Phase D) | no | no | no | no | NOT YET | future field; not available Phase B |
| matching_confidence | NO (Phase D) | no | no | no | no | NOT YET | future field; not available Phase B |
| shipping_cost (confirmed) | same as shipping_cost | yes | yes | no | no | YES (as None check) | Phase B checks is None |
| supplier_availability | NO | no | no | no | no | NOT YET | approximate via supplier_cost present |
| cj_vid | NO | no | no | no | no | NOT YET | needed for Phase 3 only |
| restricted_category_risk | NO (direct) | no | no | no | no | INDIRECT | read from filter_reasons "F1 legal:" prefix |
| branded_counterfeit_risk | NO (direct) | no | no | no | no | INDIRECT | approximated from filter_reasons if present |
| medical_claims_risk | NO | no | no | no | no | NOT YET | not detected by current scoring |
| battery_risk | NO (direct) | no | no | no | no | INDIRECT | approximated from filter_reasons "F2 shipping: hazmat" |
| fragile_risk | NO (direct) | no | no | no | no | INDIRECT | approximated from filter_reasons "F3 fragility:" prefix |

### Note on INDIRECT risk fields

Fields marked INDIRECT above (restricted_category_risk, branded_counterfeit_risk,
battery_risk, fragile_risk) are NOT available as direct input keys in Phase B.
decide_product() must NOT read product["restricted_category_risk"] or any similar
named risk key — those keys do not exist in the product dict returned by _summary(row).

Phase B MAY produce a risk_flags list as an OUTPUT by reading filter_reasons and
caution_reasons, which ARE available inputs. Example derivations:
  filter_reasons entry starting with "F1 legal:"     -> output risk_flags entry "legal_risk"
  filter_reasons entry starting with "F2 shipping: hazmat" -> output "hazmat_risk"
  filter_reasons entry starting with "F3 fragility:" -> output "fragility_risk"

risk_flags is an OUTPUT of decide_product(), not an input.
The named risk fields (restricted_category_risk, battery_risk, etc.) are not inputs,
not DB columns, and must not be referenced in decide_product() logic.

---

## 8. decision_confidence vs scoring confidence

### Two distinct confidence fields

| Field | Key in output | Value type | Source | Semantics |
|---|---|---|---|---|
| Scoring confidence | "confidence" in _summary | str: "High"/"Medium"/"Low" | scoring.py _confidence() | fraction of 19 CONFIDENCE_FIELDS that are not None |
| Decision confidence | "decision_confidence" in decide_product() output | str: "HIGH"/"MEDIUM"/"LOW" | decision_engine.py | decision-relevant field coverage |

These are different fields with different keys. They should coexist in the /products response.

### decision_confidence definition for Phase B

Phase B computes decision_confidence from the fields relevant to the decision:

  HIGH   - supplier_cost present AND retail_price present AND shipping_cost present
             AND image_url present AND scoring confidence is "Medium" or "High"
  MEDIUM - supplier_cost present AND retail_price present
             AND (shipping_cost is None or estimated safely)
             AND scoring confidence is "Low" or better
  LOW    - any of supplier_cost or retail_price is missing
             OR scoring confidence is "Low" AND critical fields absent

This separates "we have enough for a business decision" from "we have enough for
a statistically confident scoring model". Both are valid measures; they are not the same.

### Scoring confidence will be "Low" for all current live products

See finding 2 in the executive summary.
Phase B's decision cap (Cap-1) ensures no product with scoring confidence "Low"
produces a TEST decision. This is already satisfied by Phase B decision rules.
Phase B decision_confidence may be MEDIUM or HIGH even when scoring confidence
is "Low", if the decision-relevant fields (supplier_cost, retail_price,
shipping_cost) are all present. This lets a well-enriched product reach a WATCH
or TEST decision if manually entered with all fields, even before TikTok etc.

---

## 9. Frontend field consumption audit

Source: frontend/pages/index.js

### Fields read from GET /products response (list of _summary dicts)

| Field | Used where | Notes |
|---|---|---|
| p.id | row key, openDetail call | |
| p.name | displayed in all views | |
| p.source | filter, source pill display | |
| p.country | filter, display | |
| p.category | display (manual products table) | |
| p.retail_price | price display, sort | |
| p.score | score display, sort | may be null |
| p.recommendation | Pill component, filter | |
| p.confidence | confidence display (manual products table, line 664) | plain string |
| p.net_profit_per_order | display (manual products table, line 663) | |
| p.source_url | "View on source" link | |
| p.shortlisted | shortlist filter, star icon | bool |
| p.shortlisted_at | display | |
| p.review_status | status select, pipeline grouping | |
| p.operator_notes | notes display | |
| p.reviewed_at | display | |
| p.discovered_at | display (line 612) | |
| p.image_url | NOT currently rendered in list | field present but not displayed |

### Fields read from GET /products/{pid} response

The /products/{pid} response is {"product": ..., "scoring": ...}.
The frontend detail drawer (index.js:861-898) reads:

| Field | Path | Notes |
|---|---|---|
| product.name | detail.product.name | drawer heading |
| product.category | detail.product.category | sub-heading |
| product.country | detail.product.country | sub-heading |
| scoring.recommendation | detail.scoring.recommendation | Pill component |
| scoring.score | detail.scoring.score | |
| scoring.confidence.level | detail.scoring.confidence.level | FULL DICT via scoring key |
| scoring.confidence.supported | detail.scoring.confidence.supported | |
| scoring.confidence.denominator | detail.scoring.confidence.denominator | |
| scoring.eliminated | detail.scoring.eliminated | |
| scoring.filter_reasons | detail.scoring.filter_reasons | joined with "; " |
| scoring.categories | detail.scoring.categories | per-category bars |
| scoring.net_profit_per_order | detail.scoring.net_profit_per_order | |
| scoring.cac_used | detail.scoring.cac_used | |
| scoring.cautions | detail.scoring.cautions | |
| scoring.recommendation_reason | detail.scoring.recommendation_reason | |

### Critical: do not break scoring.confidence.level in drawer

The detail drawer reads detail.scoring.confidence.level (index.js:871).
This path works because /products/{pid} returns:
  {"product": <raw dict>, "scoring": score_product(p)}
and score_product() returns confidence as the full dict {"level", "supported", ...}.

If Phase B changes /products/{pid} to use _summary_with_decision(row) for "product",
the "scoring" key must remain score_product(p) unchanged.
Do NOT replace "scoring" with _summary output (which has confidence as a string).

### Decision fields: frontend safety requirement

Phase B decision fields (decision, decision_confidence, next_action, etc.) are NEW keys.
The frontend must handle these gracefully if they appear in the response:
  - A product object with an unknown key does no harm in JavaScript.
  - If the frontend references product.decision and it is undefined (null), 
    no crash occurs if the reference is guarded.
Phase B can ship backend changes before the frontend badge is added.
The frontend will ignore new keys until it explicitly reads them.

---

## 10. Phase B implementation checklist

Based on this field review, Phase B (backend/decision_engine.py) can be
implemented using only the fields confirmed in this document.

### Pre-implementation checklist (Phase A complete)

[x] DB schema audited - all columns confirmed
[x] _summary(row) output confirmed - all 28 fields listed in section 3
[x] EXPORT_FIELDS confirmed - current 21 fields listed in section 6
[x] scoring.py outputs confirmed - eliminated, filter_reasons, caution_reasons,
     positive_reasons, confidence (string in _summary), net_profit_per_order
[x] normalize_candidate() non-persisted fields confirmed - do not use from DB
[x] Frontend field consumption confirmed - no Phase B changes break existing behavior
[x] /products/{pid} confirmed as NOT using _summary - separate shape, keep scoring key intact
[x] Confidence is "Low" for all current live products - Phase B produces NEEDS_ENRICHMENT/WATCH

### Phase B implementation steps

Step 1: create backend/decision_engine.py
  - Single function: decide_product(product: dict) -> dict
  - Input: the dict returned by _summary(row) or _summary_with_decision(row)
  - No imports of db, sqlite3, requests, httpx, config, or any network/IO module
  - No side effects

Step 2: implement hard REJECT rules (check first)
  - eliminated is True -> REJECT (pass through filter_reasons)
  - filter_reasons is not [] -> REJECT (safety check)
  - supplier_cost is None AND source == "cj_dropshipping" -> REJECT (bad data)
  - supplier_cost is not None AND retail_price is not None
    AND supplier_cost >= retail_price -> REJECT
  - net_profit_per_order is not None AND net_profit_per_order < 0 -> REJECT

Step 3: implement NEEDS_ENRICHMENT rules
  - retail_price is None -> NEEDS_ENRICHMENT, next_action = "run_ebay_benchmark"
  - supplier_cost is None (non-CJ source) -> NEEDS_ENRICHMENT, next_action = "operator_review_required"
  - shipping_cost is None AND product_weight_kg >= 0.3 -> NEEDS_ENRICHMENT,
    next_action = "run_cj_shipping_enrichment" if item_id else "operator_review_required"
  - image_url is None -> flag in missing_data (may allow WATCH, blocks TEST)
  - product_weight_kg is None AND source == "cj_dropshipping"
    -> flag in missing_data, NEEDS_ENRICHMENT if no other path

Step 4: implement WATCH rules
  - positive_reasons not empty AND any ENRICH condition -> WATCH
  - shipping_cost is None AND product_weight_kg < 0.3 (estimated flat-rate safe) -> WATCH
  - confidence == "Low" (from scoring) -> cap at WATCH (never TEST)
  - caution_reasons not empty (risk overlay) -> cap at WATCH
  - recommendation in ("Watchlist",) -> WATCH unless REJECT/ENRICH applies first

Step 5: implement TEST condition (all required)
  - eliminated is False AND filter_reasons is []
  - net_profit_per_order is not None AND net_profit_per_order > 0
  - retail_price is not None AND supplier_cost is not None AND shipping_cost is not None
  - image_url is not None
  - confidence in ("High", "Medium")
  - positive_reasons not empty
  - caution_reasons is [] (no risk overlay)
  - recommendation in ("Strong candidate", "Test with small budget")
  -> TEST, next_action = "prepare_test_offer"

Step 6: implement margin_status
  - From net_profit_per_order and retail_price:
    strong_margin: net >= 35% of retail
    acceptable_margin: net 20-34% of retail
    weak_margin: net 10-19% of retail
    negative_margin: net < 0
    unknown_margin: net is None

Step 7: implement decision_confidence
  Map from field availability (see section 8) to HIGH/MEDIUM/LOW.
  Map scoring confidence ("High"/"Medium"/"Low") to uppercase for reference.

Step 8: implement missing_data list
  Check each of: retail_price, supplier_cost, shipping_cost, image_url,
  product_weight_kg (for CJ). Absent fields -> append field name to list.

Step 9: implement risk_flags list
  Derive from filter_reasons and caution_reasons already in _summary output.
  Prefix-based detection for specific risk types (F1=legal, F2=shipping, F3=fragile, etc.).

Step 10: implement decision_reasons list
  Generate readable strings for each condition that influenced the decision.
  Reference actual field values where possible.

Step 11: implement next_action
  Single action code based on decision and most critical missing field.

Step 12: implement fallback
  If no rule resolves cleanly, return NEEDS_ENRICHMENT.
  Never default to TEST.

Step 13: add import in main.py
  import decision_engine

Step 14: add _summary_with_decision() wrapper in main.py
  def _summary_with_decision(row, cac=None):
      s = _summary(row, cac)
      s.update(decision_engine.decide_product(s))
      return s

Step 15: replace _summary calls in /products and /export/products endpoints
  GET /products (line 364): replace _summary(r) with _summary_with_decision(r)
  GET /export/products (line 2777): replace _summary(row) with _summary_with_decision(row)

Step 16: extend EXPORT_FIELDS in main.py
  Append: "decision", "decision_confidence", "margin_status",
  "estimated_net_margin", "missing_data", "risk_flags", "decision_reasons",
  "next_action"

Step 17: write five unit tests (no server, no DB)
  a) negative margin -> REJECT
  b) missing shipping_cost (heavy product) -> NEEDS_ENRICHMENT
  c) complete positive product -> TEST
  d) scoring confidence "Low" -> not TEST (WATCH or NEEDS_ENRICHMENT)
  e) filter_reasons not empty -> REJECT

Step 18: run backend startup check
  python -m dotenv -f .env run -- python -m uvicorn main:app --host 0.0.0.0 --port 8000
  Confirm no ImportError or AttributeError.

Step 19: smoke test GET /products
  Confirm all products include "decision" key in response.
  Confirm all existing fields still present.

---

## 11. Confirmed non-available fields for Phase B

The following fields from PRODUCT_DECISION_ENGINE_PLAN.md cannot be used in
Phase B because they do not exist in the current codebase. They are documented
here so that Phase B code does not reference them.

| Field | Why not available | When available |
|---|---|---|
| ebay_avg_price | not in DB, not in _summary | Phase D (eBay matching) |
| ebay_median_price | not in DB, not in _summary | Phase D |
| ebay_listing_count | not in DB, not in _summary | Phase D |
| ebay_benchmark_confidence | not in DB | Phase D |
| matching_confidence | not in DB | Phase D |
| supplier_availability | not in DB | approximated; future field |
| cj_vid | not in DB | Phase E Phase 3 |
| retail_price_suggestion | not in DB | Phase E Phase 2 (CJ detail endpoint) |
| tiktok_ad_count | not in DB | pending TikTok access approval |
| google_trends_score | not in DB | pending alpha invitation |
| youtube_video_count | not in DB | pending YouTube setup approval |
| restricted_category_risk | not in DB as named field | NOT an input to decide_product(); derive risk_flags OUTPUT from filter_reasons "F1 legal:" |
| branded_counterfeit_risk | not in DB as named field | NOT an input to decide_product(); derive risk_flags OUTPUT from filter_reasons if present |
| medical_claims_risk | not in DB | not detected by current scoring; cannot be derived |
| battery_risk | not in DB as named field | NOT an input to decide_product(); derive risk_flags OUTPUT from filter_reasons "F2 shipping: hazmat" |
| fragile_risk | not in DB as named field | NOT an input to decide_product(); derive risk_flags OUTPUT from filter_reasons "F3 fragility:" |

Note: the above five fields cannot be read as product[key] inputs inside decide_product().
Phase B MAY include derived risk strings in its risk_flags OUTPUT list using
filter_reasons and caution_reasons (which are confirmed available inputs). This is the
only valid access pattern. Do not define product["battery_risk"] or similar reads.

---

## 12. Summary table

| Item | Status |
|---|---|
| DB schema audited | complete |
| _summary(row) fields confirmed | complete (28 fields, section 3) |
| scoring.py outputs confirmed | complete (section 4) |
| normalize_candidate() persistence gaps confirmed | complete (section 5) |
| EXPORT_FIELDS confirmed | complete (section 6) |
| Decision engine field mapping | complete (section 7, 55+ fields assessed) |
| Confidence field distinction documented | complete (section 8) |
| Frontend field audit | complete (section 9) |
| Phase B implementation checklist | complete (section 10, 19 steps) |
| Non-available fields listed | complete (section 11) |
| Phase A code changes | NONE |
| Phase A DB changes | NONE |
| Phase A API changes | NONE |
| Phase A .env changes | NONE |
| Phase A secret exposure | NONE |
| Phase B used only confirmed-available fields | YES - all inputs from section 7 "Phase B usable: YES" rows |
| Phase B introduced unavailable input keys | NO - section 11 fields are not read as product[key] |
| Phase B risk_flags source | filter_reasons + caution_reasons only (section 7 note on INDIRECT fields) |
| Phase B DB migration | NONE |
| Phase B new connector | NONE |
| Phase B .env changes | NONE |
| Phase B secret exposure | NONE |
| Phase B commit status | committed 8006d40 / runtime smoke test passed |
| Phase B runtime output | NEEDS_ENRICHMENT=48, REJECT=28, WATCH=0, TEST=0 (76 products) |
| Phase B output confirms | decision engine is conservative; all NEEDS_ENRICHMENT due to missing fields, not logic errors |
| Phase B missing_data distribution | image_url=71, shipping_cost=42, supplier_cost=40, retail_price=5, product_weight_kg=1 |
| Phase B next-step audit | DECISION_OUTPUT_AUDIT.md created - see section 12-13 for ranked recommendations |
