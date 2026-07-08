# Execution Bridge Plan

Last updated: 2026-07-08
Status: bridge_complete / Phase_B_committed / smoke_test_passed / audit_complete

Phase A status: COMPLETE (committed 11a7efd)
  FIELD_SCHEMA_REVIEW.md created as Phase A output. No code changes.

Phase B status: COMMITTED (8006d40) / runtime smoke test passed
  backend/decision_engine.py created - pure function decide_product(product: dict) -> dict
  backend/main.py updated - import decision_engine, _summary_with_decision() wrapper,
    GET /products and GET /export/products use wrapper, EXPORT_FIELDS extended.
  backend/test_decision_engine.py created - stdlib unittest, 51 tests pass, no server, no DB.
  GET /products/{pid} NOT changed - returns raw product + scoring.score_product() unchanged.
  No DB migration. No new connector. No external APIs called.
  backend/.env was not modified and was not printed.
  python-dotenv may have loaded env vars during startup import check only.
  No secrets exposed in code, tests, or docs.

Runtime smoke test (2026-07-08):
  76 products evaluated. NEEDS_ENRICHMENT=48, REJECT=28, WATCH=0, TEST=0.
  All 8 decision fields confirmed on /products and /export/products.
  /products/{pid} confirmed unchanged. scoring.confidence.level intact.
  See DECISION_OUTPUT_AUDIT.md for full source-level breakdown and next-step analysis.

This file connects:
- the strategic product decision plan (PRODUCT_DECISION_ENGINE_PLAN.md)
- the source strategy map (SOURCE_STRATEGY_MAP.md)
- the actual repo structure (verified by reading source files)
- the next executable engineering phase (Phase A -> Phase B)

---

## 1. Executive summary

PRODUCT_DECISION_ENGINE_PLAN.md defines what the decision engine must produce:
a decision (TEST/WATCH/NEEDS_ENRICHMENT/REJECT), a confidence level, a set of
reasons, a missing data list, and a next action for the operator.

This file bridges that strategic plan to the specific files, functions, and
integration points in the actual codebase.

Key findings from the code audit:

- The scoring engine (backend/scoring.py) already produces filter_reasons,
  caution_reasons, positive_reasons, confidence level, and net_profit_per_order.
  These are exactly the inputs the decision engine needs. It does not need to
  re-implement scoring logic.

- The summary helper (_summary, main.py:160) already assembles all scoring
  results plus DB fields into a flat dict returned from /products and
  /export/products. The decision engine can receive this dict as input.

- The decision engine is a pure function on top of existing outputs.
  No new DB columns. No new API calls. No schema migration.
  Phase B adds one file: backend/decision_engine.py.

- Most live CJ products will produce NEEDS_ENRICHMENT decisions in Phase B
  because CJ live mode does not return retail_price or shipping_cost.
  This is the expected and useful output: it confirms exactly which enrichment
  phases (CJ Phase 2 / Phase 3) are the highest-priority next step.

---

## 2. Current code reality

### File inventory (confirmed by reading source)

  backend/main.py
    The FastAPI application layer. Owns:
    - _summary(row, cac=None) at line 160
      Core helper: takes a DB row dict, calls score_product(), returns flat
      product dict used by /products and /export/products.
      NOT currently called by /products/{pid} — that endpoint returns raw
      product dict + scoring separately (see below).
    - GET /products (line 364): returns [_summary(r) for r in db.fetch_all()]
    - GET /products/{pid} (line 369): returns {"product": p, "scoring": score_product(p)}
    - GET /export/products (line 2766): calls _summary(row), filters, picks EXPORT_FIELDS
    - EXPORT_FIELDS (line 2749): the field list for /export/products output
    - POST /products/{pid}/shortlist (line 378): toggle shortlisted flag
    - PATCH /products/{pid}/review (line 391): update review_status / operator_notes
    - POST /discovery/manual: manual product input
    - POST /discovery/multisource: multisource discovery

  backend/scoring.py
    Pure deterministic scoring engine. No DB. No network. Exports:
    - score_product(p, cac=DEFAULT_CAC) -> dict
      Input: product dict with any combination of scoring fields
      Output: eliminated, filter_reasons, cautions, caution_reasons,
              score (/60), score_max, categories, score_breakdown,
              positive_reasons, confidence {level, supported, denominator, percent},
              net_profit_per_order, cac_used, base_verdict, recommendation,
              recommendation_reason
    - run_filters(p) -> {status, reasons, cautions}
      Hard filter logic: F1 legal, F2 shipping, F3 fragility, F4 seasonality,
      F5 market fit, F6 fad-collapse, F7 digital, F8 gross margin.
    - compute_net(p, cac) -> float | None
      Net margin: retail_price - supplier_cost - shipping_cost - cac
    - DEFAULT_CAC = 20.0
    - VERDICT_ORDER = ["Reject", "Watchlist", "Test with small budget", "Strong candidate"]
    - confidence levels: "Low" | "Medium" | "High"
    - recommendation values: "Reject" | "Watchlist" | "Test with small budget" | "Strong candidate"

  backend/db.py
    SQLite data layer. Exports:
    - init_db(): creates/migrates products and market_evidence tables
    - fetch_all(): returns all product rows (sqlite3.Row objects)
    - fetch_by_id(pid): returns one product row by id
    - upsert_discovered_candidate(candidate): dedup insert from connectors
    - toggle_shortlist(pid): sets shortlisted flag
    - update_review_fields(pid, review_status, operator_notes)
    - ALLCOLS: all writable column names
    Products table columns (confirmed from CREATE TABLE + ALTER TABLE migration):
      id, name, category, country, created_at,
      trends_interest, amazon_bsr, reddit_posts_90d, pinterest_saves,
      trends_direction_pct, seasonality_ratio, tiktok_momentum,
      supplier_cost, shipping_cost, retail_price, product_weight_kg,
      tiktok_hashtag_views, meta_active_advertisers, meta_ad_longevity_days,
      demo_videos_top10, aliexpress_sellers_1k, brand_dominance_pct,
      competitor_count, diff_unaddressed_themes, diff_complement_skus,
      diff_oem_available, diff_market_fragmented, diff_organic_ugc,
      legal_restricted, hazmat, fragile_material, breakage_mentions,
      longest_dim_cm, seasonality_offpeak, alltime_current_value,
      [migrated via ALTER TABLE]: source, source_url, item_id, image_url,
      score, recommendation, discovered_at, shortlisted, shortlisted_at,
      review_status, operator_notes, reviewed_at

  backend/sources/normalize.py
    normalize_candidate(p, source, query, score_result) -> dict
    Already produces: missing_data (list of absent signal fields),
    risk_flags (from score cautions), demand_signal, margin_signal, etc.
    This function runs at discovery time. The DB row does not store normalize output.

  backend/sources/connectors/__init__.py
    CONNECTORS dict: maps source name to BaseConnector instance.
    Active live connectors: ebay (EbayOfficialConnector), cj_dropshipping (CjConnector).
    Pending connectors: tiktok_ads (pending_access), google_trends_official (pending_access).
    Not implemented: youtube, reddit, amazon, keepa, aliexpress, meta.
    YouTubeConnector stub already exists (implemented = False, required_env_vars = ["YOUTUBE_API_KEY"]).

  backend/sources/cj_dropshipping.py / backend/sources/ebay.py
    Frozen. Do not modify.

  frontend/pages/index.js
    Single-page dashboard. Reads /products for the product list.
    Existing flow: discover -> shortlist -> review -> export.
    Review statuses: new | researching | test_candidate | rejected | winner.
    This is the only frontend file. Do not redesign.

### What _summary(row) currently returns

The fields in the dict returned by _summary(row) (main.py:160) are:

  id, name, category, country, source, item_id, source_url, image_url,
  discovered_at, retail_price, supplier_cost, shipping_cost, product_weight_kg,
  shortlisted, shortlisted_at, review_status, operator_notes, reviewed_at,
  score, score_max (=60), recommendation, confidence (level string),
  net_profit_per_order, eliminated, positive_reasons, caution_reasons,
  filter_reasons, score_breakdown

### What EXPORT_FIELDS currently contains (main.py:2749)

  "id", "name", "category", "country", "source", "item_id", "source_url",
  "image_url", "retail_price", "supplier_cost", "shipping_cost",
  "product_weight_kg", "score", "recommendation",
  "shortlisted", "shortlisted_at", "review_status", "operator_notes",
  "reviewed_at", "discovered_at"

---

## 3. What must NOT change in Phase B

No DB migration.
  Do not add columns to the products table.
  Do not run ALTER TABLE.
  Decision output is computed at query time and returned dynamically.
  No decision fields are persisted in Phase B.

No new connector.
  Do not add a new source to CONNECTORS.
  Do not implement YouTubeConnector (implemented = False stays).
  Do not touch backend/sources/connectors/__init__.py.

No YouTube implementation.
  YouTubeConnector stub already exists. Leave it alone.
  YOUTUBE_API_KEY is not set. Do not create one.
  Do not call the YouTube Data API.

No CJ Phase 2 or Phase 3 implementation.
  Do not call GET /v1/product/query?pid= (CJ detail endpoint).
  Do not call POST /v1/logistic/freightCalculate (CJ shipping).
  Do not modify backend/sources/cj_dropshipping.py.

No changes to backend/.env.
  No new keys. No new tokens. No new environment variables added to .env.

No new external API calls.
  decide_product() must be pure. No network inside the function.

No secrets.
  No API keys or tokens in code or documentation.

No breaking API changes.
  /products and /export/products: all existing fields must remain unchanged.
  Decision fields are ADDITIVE. Existing clients that ignore unknown fields
  will not break. Existing clients that enumerate known fields will still work.
  /products/{pid}: currently returns {"product": <raw row dict>, "scoring": <full scoring>}.
  It does NOT currently use _summary. Phase B may optionally align it by using
  _summary_with_decision for the "product" key while keeping "scoring" unchanged.
  If /products/{pid} is aligned, existing fields in both sub-objects must be preserved.

---

## 4. Recommended implementation target

### Phase B definition

Create: backend/decision_engine.py

Exports one public function:

  decide_product(product: dict) -> dict

Properties of decide_product:
  - Pure function. No imports of db, no sqlite3, no requests, no httpx.
  - Receives the dict already assembled by _summary(row). All scoring results
    and DB field values are present in that dict.
  - Returns the decision output dict (shape in section 5).
  - Deterministic: same input always produces same output.
  - Testable with static dicts: no test setup required, no mocking.
  - No side effects.

Integration: call from _summary(row) in main.py

  Current _summary return dict ends at "score_breakdown".
  After Phase B, _summary merges in the decide_product output:

    summary = {
        "id": ...,
        ...existing fields unchanged...
        "score_breakdown": res.get("score_breakdown", {}),
    }
    summary.update(decision_engine.decide_product(summary))
    return summary

  This means:
  - GET /products automatically includes decision fields (calls _summary_with_decision).
  - GET /products/{pid}: does NOT currently call _summary. Current shape is
    {"product": <raw row dict>, "scoring": score_product(p)}. The decision merge
    does NOT happen automatically here. Phase B option: call _summary_with_decision(row)
    for the "product" key while keeping "scoring" unchanged. This alignment is optional
    in Phase B. Document the decision in FIELD_SCHEMA_REVIEW.md before implementing.
  - GET /export/products: calls _summary(row) already. Replace with
    _summary_with_decision. EXPORT_FIELDS must be extended (see section 10).

### Alternative: keep _summary clean, wrap it

If merging into _summary is too invasive for Phase B risk tolerance, the
alternative is:

  def _summary_with_decision(row, cac=None):
      s = _summary(row, cac)
      s.update(decision_engine.decide_product(s))
      return s

Then replace _summary calls in /products and /export/products with
_summary_with_decision. This keeps the existing _summary untouched.

Either approach is valid. The wrapper approach has lower blast radius.

---

## 5. Proposed decision output object

decide_product(product: dict) returns exactly this shape:

  {
    "decision":             "TEST" | "WATCH" | "NEEDS_ENRICHMENT" | "REJECT",
    "decision_confidence":  "HIGH" | "MEDIUM" | "LOW",
    "margin_status":        "strong_margin" | "acceptable_margin" | "weak_margin"
                            | "unknown_margin" | "negative_margin",
    "estimated_net_margin": <float> | null,
    "missing_data":         [ <string>, ... ],
    "risk_flags":           [ <string>, ... ],
    "decision_reasons":     [ <string>, ... ],
    "next_action":          "prepare_test_offer"
                            | "run_cj_shipping_enrichment"
                            | "run_ebay_benchmark"
                            | "run_cj_detail_enrichment"
                            | "keep_watchlist"
                            | "reject_product"
                            | "operator_review_required"
  }

### Note on confidence level casing

scoring.py uses "High" / "Medium" / "Low" (title case) for the confidence level
stored in the _summary output under the key "confidence".

The decision engine output uses "HIGH" / "MEDIUM" / "LOW" (uppercase) for the
key "decision_confidence". These are two distinct keys with consistent individual
conventions. Do not rename the existing "confidence" key.

### Note on existing recommendation field

scoring.py already returns a "recommendation" field with values:
  "Strong candidate" | "Test with small budget" | "Watchlist" | "Reject"

The decision engine "decision" field (TEST / WATCH / NEEDS_ENRICHMENT / REJECT)
is a different field with a different key. It does not replace "recommendation".
Both fields coexist in the output. Operators can see both the score-based
recommendation and the decision-engine decision. They will often agree; when they
differ (e.g., recommendation says "Test with small budget" but decision says
NEEDS_ENRICHMENT because shipping is missing), the decision engine output is the
actionable one.

---

## 6. Field mapping from current DB and API output

The following table shows which decision engine inputs are already available
in the dict that _summary(row) returns, and how Phase B handles missing ones.

| Decision engine input | In _summary? | Current key | Missing condition | Phase B behavior |
|---|---|---|---|---|
| name | yes | "name" | never None (DB NOT NULL) | direct read |
| category | yes | "category" | may be None or "other" | default to "other" |
| country | yes | "country" | may be None | default to "US" |
| source | yes | "source" | may be None (manual entry) | read; None is OK |
| source_url | yes | "source_url" | commonly None for CJ and eBay | note in missing_data if needed |
| retail_price | yes | "retail_price" | None for all live CJ products | NEEDS_ENRICHMENT trigger |
| supplier_cost | yes | "supplier_cost" | None for eBay-only products | NEEDS_ENRICHMENT or REJECT trigger |
| shipping_cost | yes | "shipping_cost" | None for all current live products | NEEDS_ENRICHMENT trigger |
| product_weight_kg | yes | "product_weight_kg" | None for eBay products; present for CJ | NEEDS_ENRICHMENT trigger for CJ |
| image_url | yes | "image_url" | None for eBay (Browse API sometimes omits) | note in missing_data |
| score | yes | "score" | None if eliminated=True | check eliminated first |
| recommendation | yes | "recommendation" | always present (Reject/Watchlist/etc.) | use as secondary signal |
| confidence | yes | "confidence" (level string) | always present (Low/Medium/High) | map to HIGH/MEDIUM/LOW |
| net_profit_per_order | yes | "net_profit_per_order" | None if any of retail/cost/ship is missing | NEEDS_ENRICHMENT trigger |
| positive_reasons | yes | "positive_reasons" | [] when absent | check len > 0 |
| caution_reasons | yes | "caution_reasons" | [] when absent | read for WATCH signal |
| filter_reasons | yes | "filter_reasons" | [] when no hard filters | non-empty = REJECT |
| eliminated | yes | "eliminated" | always present (bool) | True = hard REJECT |
| review_status | yes | "review_status" | always present (default "new") | read for context |
| shortlisted | yes | "shortlisted" | always present (bool) | read for context |
| estimated_net_margin | derived | compute from retail/cost/ship | same as net_profit_per_order | use existing value |

### Fields NOT present in _summary (Phase A must confirm)

The following decision inputs from PRODUCT_DECISION_ENGINE_PLAN.md are NOT
in the current _summary output. Phase A field review will confirm this and
determine whether they are present in the raw DB row but excluded from _summary:

- ebay_avg_price, ebay_median_price, ebay_listing_count, ebay_benchmark_confidence
  These were defined in the plan as future eBay enrichment output. Not in DB schema.
  Phase B: treat retail_price as the proxy for market benchmark.

- matching_confidence
  Not in DB. Not in _summary. Defined in plan as a future field.
  Phase B: not available. Note in decision_reasons if retail_price is None.

- supplier_availability
  Not explicitly stored. CJ live call confirms availability implicitly (product appears in results).
  Phase B: treat supplier_cost presence from CJ as evidence of availability.

- cj_pid, cj_vid
  item_id in DB maps to CJ product ID (pid). cj_vid is not stored (needed for Phase 3 shipping).
  Phase B: item_id is available as a reference for future enrichment.

- risk fields (restricted_category_risk, branded_counterfeit_risk, medical_claims_risk, etc.)
  These are approximated by filter_reasons from scoring.py run_filters():
  - F1 legal -> restricted_category_risk equivalent
  - F2 shipping: hazmat -> battery/compliance risk equivalent
  - F3 fragility -> fragile_risk equivalent
  - F7 digital -> non-shippable equivalent
  Phase B: read from filter_reasons. No separate risk field needed.

---

## 7. Phase B decision rules based only on existing fields

These rules operate entirely on the dict returned by _summary(row).
No new DB columns required. No new API calls required.

### Hard REJECT conditions (check first, before any other logic)

REJECT-01: eliminated = True
  scoring.run_filters() already determined this product fails hard conditions.
  filter_reasons is non-empty. Trust the scoring engine's filter result.
  decision_reasons = filter_reasons (pass through)
  next_action = "reject_product"

REJECT-02: filter_reasons is non-empty (redundant safety check)
  Even if eliminated is somehow False, non-empty filter_reasons = REJECT.
  F1 legal, F2 shipping excess, F3 fragility+breakage, F4 seasonality off-peak,
  F5 no demand, F6 fad-collapse, F7 digital, F8 negative gross margin all
  produce filter_reasons entries.

REJECT-03: supplier_cost is None AND source == "cj_dropshipping"
  CJ is a supplier source. If supplier_cost is None from a CJ product, data is bad.
  decision_reasons = ["CJ product missing supplier_cost — cannot evaluate"]
  next_action = "reject_product"

REJECT-04: retail_price is not None AND supplier_cost is not None
           AND supplier_cost >= retail_price
  No margin room. Cost at or above retail price.
  decision_reasons = ["Supplier cost equals or exceeds retail benchmark"]
  next_action = "reject_product"

REJECT-05: net_profit_per_order is not None AND net_profit_per_order < 0
  scoring.compute_net() already computed this. Negative net margin.
  decision_reasons = [f"Estimated net margin is negative: ${net_profit_per_order:.2f}"]
  next_action = "reject_product"

### NEEDS_ENRICHMENT conditions (check after REJECT, before WATCH/TEST)

ENRICH-01: retail_price is None
  Cannot compute margin. Cannot confirm market benchmark.
  missing_data = ["retail_price"]
  next_action = "run_ebay_benchmark" (or "run_cj_detail_enrichment" if source is CJ)
  Note: this is the most common condition for live CJ products.

ENRICH-02: supplier_cost is None AND source != "cj_dropshipping"
  Source is eBay or manual. Supplier cost not provided.
  missing_data includes "supplier_cost"
  next_action = "operator_review_required"

ENRICH-03: shipping_cost is None
  Cannot compute net margin. Cannot confirm TEST viability.
  Exception: if product_weight_kg < 0.3 AND margin appears strong even at
  estimated flat-rate shipping ($4 assumption), may allow WATCH instead.
  See WATCH-02 below.
  missing_data includes "shipping_cost"
  next_action = "run_cj_shipping_enrichment" if item_id present, else "operator_review_required"

ENRICH-04: image_url is None
  Cannot prepare an offer. Cannot display product to end customer.
  missing_data includes "image_url"
  Note: this alone does not necessarily block WATCH. Blocks TEST.

ENRICH-05: product_weight_kg is None AND source == "cj_dropshipping"
  CJ should provide weight. Missing weight means data is incomplete.
  missing_data includes "product_weight_kg"
  next_action = "run_cj_detail_enrichment"

ENRICH-06: net_profit_per_order is None (any required field missing)
  If net cannot be computed, decision cannot reach TEST.
  missing_data = [field for field in ("retail_price", "supplier_cost", "shipping_cost")
                  if product.get(field) is None]
  next_action: depends on which field is missing (see above).

### WATCH conditions

WATCH-01: positive_reasons not empty AND any ENRICH condition applies
  Product looks promising (scoring found positive signals) but critical data
  is missing. Use WATCH with the NEEDS_ENRICHMENT next_action to signal
  this is worth resolving.
  decision_confidence: "MEDIUM" or "LOW" depending on confidence level.
  decision_reasons = positive_reasons + ["Missing: {field}"]

WATCH-02: shipping_cost is None AND product_weight_kg < 0.3
  Lightweight product. Estimated flat-rate shipping ($4 USD) is reasonable.
  If estimated net margin with flat-rate shipping is still positive, upgrade
  from NEEDS_ENRICHMENT to WATCH.
  decision_reasons include: "Shipping cost estimated at flat rate ($4) due to
  lightweight product (Xkg). Not confirmed. Test not yet approved."
  decision_confidence: "MEDIUM" maximum.
  next_action: "keep_watchlist"
  NOTE: never produce TEST from an estimated shipping cost in Phase B.

WATCH-03: confidence == "Low" (from scoring)
  Even if margin looks positive, Low confidence means not enough data.
  decision_confidence = "LOW"
  Cap at WATCH: never TEST when confidence is Low.
  next_action: "keep_watchlist"

WATCH-04: caution_reasons not empty (risk overlay from scoring)
  scoring._recommend() already capped the recommendation at "Watchlist" due to
  risk overlay cautions. Respect this cap. Decision = WATCH.

WATCH-05: recommendation == "Watchlist"
  Scoring engine already produced Watchlist as the final verdict.
  Decision = WATCH unless a REJECT or ENRICH condition applies first.

### TEST conditions (all must be true)

TEST requires ALL of the following:
- eliminated = False
- filter_reasons = []
- net_profit_per_order is not None AND net_profit_per_order > 0
- retail_price is not None
- supplier_cost is not None
- shipping_cost is not None (confirmed, not estimated)
- image_url is not None
- confidence in ("High", "Medium") (from _summary "confidence" field)
- positive_reasons not empty (at least one positive scoring signal)
- no caution_reasons that impose a hard Watchlist cap
- recommendation in ("Strong candidate", "Test with small budget")

If all conditions pass:
  decision = "TEST"
  decision_confidence = "HIGH" if confidence == "High" else "MEDIUM"
  next_action = "prepare_test_offer"

Note: in Phase B, very few live products will reach TEST because shipping_cost
is almost universally None for current live CJ + eBay data. This is expected.
The NEEDS_ENRICHMENT output on most products is the useful Phase B finding.

---

## 8. Decision caps

These caps are absolute. They override score-based logic.

  Cap-1: confidence == "Low" (from scoring)
    Cannot produce TEST decision.
    Maximum allowed: WATCH or NEEDS_ENRICHMENT.

  Cap-2: unknown_margin (net_profit_per_order is None)
    Cannot produce TEST decision.
    Maximum allowed: WATCH (if positive signals exist) or NEEDS_ENRICHMENT.

  Cap-3: shipping_cost is None AND product_weight_kg >= 0.3 (or missing)
    Cannot produce TEST decision (shipping estimate not safe for heavy products).
    May produce WATCH if lightweight exception (section 7 WATCH-02) applies.
    Otherwise NEEDS_ENRICHMENT.

  Cap-4: any hard risk filter triggered (filter_reasons not empty)
    Always REJECT. No exception.
    Risk filters in scoring.py: F1 legal, F2 shipping complexity, F3 fragility,
    F4 seasonality, F5 no demand, F6 fad-collapse, F7 digital, F8 gross margin.

  Cap-5: supplier_cost is None
    Cannot produce TEST decision.
    Cannot confirm margin. Maximum: NEEDS_ENRICHMENT.

  Cap-6: retail_price is None
    Cannot produce TEST decision.
    No market benchmark. Maximum: NEEDS_ENRICHMENT.

  Cap-7: image_url is None
    Cannot produce TEST decision.
    Cannot prepare an offer. Maximum: WATCH (if other signals good).

  Cap-8: fallback default
    If none of the REJECT/ENRICH/WATCH/TEST conditions resolve cleanly,
    default to NEEDS_ENRICHMENT. Never default to TEST.
    The decision engine must be conservative: over-enrichment is cheaper
    than over-promotion of incomplete products.

---

## 9. API integration plan

### Where _summary(row) currently builds its output

File: backend/main.py
Function: _summary(row, cac=None) starting at line 160

Current flow:
  1. p = dict(row)
  2. res = scoring.score_product(p, cac)
  3. Build and return a flat dict with fields from both p and res.

Phase B integration:

  Step 1: at top of main.py, add:
    import decision_engine

  Step 2: in _summary, after building the return dict (or in a wrapper),
    call decide_product with the assembled summary dict and merge the result.

  Wrapper approach (lower blast radius):

    def _summary_with_decision(row, cac=None):
        s = _summary(row, cac)
        s.update(decision_engine.decide_product(s))
        return s

  Replace calls to _summary in:
    - GET /products (line 364): [_summary_with_decision(r) for r in db.fetch_all()]
    - GET /export/products (line 2776): s = _summary_with_decision(row)

  Leave the existing _summary function intact. The wrapper is a one-line addition.

### /products/{pid} alignment

Current GET /products/{pid} (line 369) returns {"product": p, "scoring": score_product(p)}.
It does NOT currently call _summary. The response shape is different from /products.

Phase B option for /products/{pid}:
  Return the _summary_with_decision output as "product" in the response,
  plus the raw full scoring dict as "scoring" (unchanged).
  This makes /products/{pid} consistent with /products list shape.

  Result: GET /products/{pid} returns:
  {
    "product": _summary_with_decision(row),  <- includes decision fields
    "scoring": scoring.score_product(p)      <- full scoring detail unchanged
  }

### Existing fields unchanged

All current _summary fields remain:
  id, name, category, country, source, item_id, source_url, image_url,
  discovered_at, retail_price, supplier_cost, shipping_cost, product_weight_kg,
  shortlisted, shortlisted_at, review_status, operator_notes, reviewed_at,
  score, score_max, recommendation, confidence, net_profit_per_order,
  eliminated, positive_reasons, caution_reasons, filter_reasons, score_breakdown

Decision fields are ADDED alongside these, not replacing them.

Frontend clients that read any of the above fields by name will not break.
Clients that enumerate all keys will see new keys appended.

---

## 10. Export integration plan

### Current EXPORT_FIELDS (main.py:2749)

  "id", "name", "category", "country", "source", "item_id", "source_url",
  "image_url", "retail_price", "supplier_cost", "shipping_cost",
  "product_weight_kg", "score", "recommendation",
  "shortlisted", "shortlisted_at", "review_status", "operator_notes",
  "reviewed_at", "discovered_at"

### Phase B extension

Add to EXPORT_FIELDS (additive, non-breaking):

  "decision", "decision_confidence", "margin_status", "estimated_net_margin",
  "missing_data", "risk_flags", "decision_reasons", "next_action"

Since /export/products uses {f: s.get(f) for f in EXPORT_FIELDS}, any new
field in EXPORT_FIELDS will be picked from the _summary_with_decision output
automatically. No other change required.

For CSV format: list fields (missing_data, risk_flags, decision_reasons) will
be serialized by csv.DictWriter as their repr string (e.g., "['field1', 'field2']").
This is the existing behavior for any list field. If a cleaner CSV format is
desired, JSON-encode these fields before writing. This is a display decision,
not a correctness blocker for Phase B.

### No breaking changes

Existing export clients (if any) that request GET /export/products?format=json
or format=csv receive all existing fields plus new ones. JSON clients that
iterate known keys are unaffected. CSV clients that load by column name will
see new columns appended after existing ones. No column is removed or renamed.

---

## 11. Frontend integration plan

Phase B minimal frontend changes. Do not redesign the UI.
Keep the existing shortlist/review pipeline unchanged.

### Proposed additions (one at a time, not all at once)

Display decision badge in the product list table.
  Add a colored badge cell showing decision value:
  TEST (green), WATCH (yellow), NEEDS_ENRICHMENT (orange), REJECT (red).
  Read from product.decision in the /products response.
  If product.decision is undefined (before Phase B is deployed), badge is absent.

Display next_action below the badge or as a tooltip.
  Read from product.next_action.
  Example: "Run CJ shipping enrichment" as a text note below the badge.

Show decision_reasons and missing_data in existing detail view.
  The existing UI likely has some expandable area or detail view.
  Add a "Decision reasons" section showing decision_reasons as a bullet list.
  Add a "Missing data" section showing missing_data as a comma-separated list.

Do not add new routes or new pages for Phase B.
Do not modify the shortlist endpoint or review status flow.
Do not change the existing product card layout beyond adding the badge.

### Frontend resilience requirement

The frontend must handle the case where decision fields are absent (null or
undefined) without crashing. This is standard defensive rendering.
If product.decision is null, the badge simply renders nothing.
This allows phased rollout: backend Phase B can deploy before the frontend
badge is added, and the frontend change can deploy independently.

---

## 12. Test plan

### Unit tests for backend/decision_engine.py

All tests use static product dicts. No DB setup. No server needed.

Test suite structure:

  import decision_engine

  def test_negative_margin_is_reject():
      p = {
          "name": "Test Product",
          "retail_price": 10.0,
          "supplier_cost": 12.0,   # cost > retail
          "shipping_cost": 3.0,
          "image_url": "http://example.com/img.jpg",
          "confidence": "High",
          "eliminated": False,
          "filter_reasons": [],
          "positive_reasons": ["Strong demand"],
          "caution_reasons": [],
          "net_profit_per_order": -5.0,   # pre-computed by scoring
          "recommendation": "Reject",
      }
      result = decision_engine.decide_product(p)
      assert result["decision"] == "REJECT"
      assert result["next_action"] == "reject_product"

  def test_missing_shipping_is_needs_enrichment():
      p = {
          "name": "Test Product",
          "retail_price": 30.0,
          "supplier_cost": 8.0,
          "shipping_cost": None,    # missing
          "product_weight_kg": 0.8, # >= 0.3, cannot estimate safely
          "image_url": "http://example.com/img.jpg",
          "confidence": "High",
          "eliminated": False,
          "filter_reasons": [],
          "positive_reasons": ["Strong demand"],
          "caution_reasons": [],
          "net_profit_per_order": None,   # None because shipping missing
          "recommendation": "Test with small budget",
      }
      result = decision_engine.decide_product(p)
      assert result["decision"] == "NEEDS_ENRICHMENT"
      assert "shipping_cost" in result["missing_data"]
      assert result["next_action"] == "run_cj_shipping_enrichment"

  def test_complete_positive_product_is_test():
      p = {
          "name": "Posture Corrector",
          "category": "health",
          "source": "cj_dropshipping",
          "retail_price": 29.99,
          "supplier_cost": 6.50,
          "shipping_cost": 4.00,
          "product_weight_kg": 0.25,
          "image_url": "http://example.com/img.jpg",
          "confidence": "High",
          "eliminated": False,
          "filter_reasons": [],
          "positive_reasons": ["Strong demand", "Healthy profit margin"],
          "caution_reasons": [],
          "net_profit_per_order": 15.49,
          "recommendation": "Test with small budget",
      }
      result = decision_engine.decide_product(p)
      assert result["decision"] == "TEST"
      assert result["decision_confidence"] in ("HIGH", "MEDIUM")
      assert result["next_action"] == "prepare_test_offer"

  def test_low_confidence_cannot_be_test():
      p = {
          "name": "Unknown Product",
          "retail_price": 25.0,
          "supplier_cost": 5.0,
          "shipping_cost": 3.0,
          "image_url": "http://example.com/img.jpg",
          "confidence": "Low",    # Low confidence cap applies
          "eliminated": False,
          "filter_reasons": [],
          "positive_reasons": [],
          "caution_reasons": [],
          "net_profit_per_order": 17.0,
          "recommendation": "Watchlist",
      }
      result = decision_engine.decide_product(p)
      assert result["decision"] in ("WATCH", "NEEDS_ENRICHMENT")
      assert result["decision"] != "TEST"
      assert result["decision_confidence"] == "LOW"

  def test_hard_filter_reason_is_reject():
      p = {
          "name": "Restricted Item",
          "retail_price": 50.0,
          "supplier_cost": 10.0,
          "shipping_cost": 5.0,
          "image_url": "http://example.com/img.jpg",
          "confidence": "High",
          "eliminated": True,
          "filter_reasons": ["F1 legal: restricted/prohibited class"],
          "positive_reasons": [],
          "caution_reasons": [],
          "net_profit_per_order": 15.0,
          "recommendation": "Reject",
      }
      result = decision_engine.decide_product(p)
      assert result["decision"] == "REJECT"
      assert result["next_action"] == "reject_product"

### Integration tests (after Phase B backend is wired in)

  Backend startup check:
    From backend/ directory:
    python -m dotenv -f .env run -- python -m uvicorn main:app --host 0.0.0.0 --port 8000
    Server must start without ImportError or AttributeError.

  Health check:
    GET http://localhost:8000/health
    Expect: 200 OK with status field.

  Products list check:
    GET http://localhost:8000/products
    Expect: 200 OK, array of product objects.
    Each product must include "decision" key (one of TEST/WATCH/NEEDS_ENRICHMENT/REJECT).
    Each product must include "next_action" key.
    Existing fields (score, recommendation, confidence) must still be present.

  Export JSON check:
    GET http://localhost:8000/export/products?format=json
    Expect: JSON response with "products" array.
    Each product in array must include "decision" and "next_action" keys.
    Existing EXPORT_FIELDS fields must all be present.

  Export CSV check:
    GET http://localhost:8000/export/products?format=csv
    Expect: CSV file with new columns "decision", "next_action" appended.
    Existing columns must all be present and correctly ordered.

  Frontend load check:
    Confirm frontend loads without JS error.
    Product list must display (no crash from new decision fields).
    Existing shortlist / review buttons must work.

---

## 13. Risk controls

No persistence in Phase B.
  decide_product() never writes to the DB.
  No INSERT, no UPDATE, no ALTER TABLE from decision_engine.py.

No schema migration.
  Phase B requires zero DB changes.
  If all goes wrong, remove the import of decision_engine and the
  .update() call in _summary. The backend reverts immediately.

No API calls.
  decision_engine.py imports: only standard library. No requests, no httpx,
  no db, no config, no external packages.

Pure deterministic function.
  Same input always produces same output.
  Safe to run in unit tests, regression checks, and CI without any setup.

Additive fields only.
  New keys are added to existing dicts. No existing keys are removed.
  No existing values are changed.

Fallback-safe default.
  If the decision logic produces no clear result, return NEEDS_ENRICHMENT.
  Never default to TEST. The cost of under-promotion (more manual review)
  is far lower than the cost of over-promotion (wasted test spend).

Conservative Phase B scope.
  Phase B does not attempt to implement the full scoring model from
  PRODUCT_DECISION_ENGINE_PLAN.md. It uses only the fields already computed
  by the existing scoring engine. New scoring components (ebay_benchmark,
  matching_confidence, YouTube signals) wait for later phases.

---

## 14. Phase A before Phase B

### What Phase A is

Phase A is a FIELD_SCHEMA_REVIEW.md document (not code).

Phase A answers three questions:
1. Which decision engine input fields are ALREADY in the _summary(row) output?
2. Which decision engine input fields are in the DB but NOT in _summary?
3. Which decision engine input fields do not exist anywhere yet?

Phase A requires:
- Read backend/db.py CREATE TABLE and ALTER TABLE statements (already done in this audit).
- Read backend/main.py _summary(row) function (already done in this audit).
- Read backend/scoring.py score_product output fields (already done in this audit).
- Do NOT run code. Do NOT make API calls. Do NOT start the backend.

Phase A output: FIELD_SCHEMA_REVIEW.md

The document must include:
- Table: field name | in DB? | in _summary? | in scoring output? | action for Phase B
- Confirmed list of fields available to decide_product() in Phase B
- Confirmed list of fields that need to be added to _summary (if any)
- Confirmed list of fields that cannot be used in Phase B (not yet in codebase)
- Implementation checklist for Phase B (one line per step)

### Why Phase A is a separate step

This execution bridge (EXECUTION_BRIDGE_PLAN.md) already performed most of the
Phase A field audit work as part of writing section 6. However, Phase A should
produce a standalone, clearly formatted FIELD_SCHEMA_REVIEW.md document that
an engineer can use as a checklist when writing backend/decision_engine.py.

The bridge plan is strategic and design-oriented.
The field schema review is an implementation checklist.
They serve different readers.

### Phase A vs Phase B timing

Phase A (FIELD_SCHEMA_REVIEW.md) can be created in the same work session as
Phase B (decision_engine.py). Phase A does not require external approval.
It is a documentation task only. Write Phase A first, then implement Phase B.

---

## 15. Concrete next engineering step

### Step 1 (immediate): Phase A Field/Schema Review

Create FIELD_SCHEMA_REVIEW.md.
Review the actual DB columns, _summary output, and score_product output.
Produce the implementation checklist for decision_engine.py.
No code. No API calls. No secrets. No commit required until reviewed.

### Step 2: Phase B Dynamic Decision Output

Create backend/decision_engine.py.
Implement decide_product(product: dict) -> dict.
Wire into _summary_with_decision() wrapper in main.py.
Extend EXPORT_FIELDS in main.py.
Add five unit tests.
Run backend startup + smoke GET /products.

### What is NOT next

Not YouTube setup.
  YouTube Data API setup is pending owner approval. It is not needed for
  Phase A or Phase B. The decision engine works on CJ + eBay data only.

Not CJ Phase 2/3.
  Phase B will show which enrichment is most commonly needed (by counting
  NEEDS_ENRICHMENT reasons across live products). That output is the input
  to the CJ Phase 2 vs Phase 3 priority decision. Run Phase B first.

Not DB migration.
  No new columns needed in Phase B. Schema migration is a Phase C task.

Not YouTube connector implementation.
  YouTubeConnector already exists as a stub in connectors/__init__.py
  (implemented = False). Leave it. Do not set YOUTUBE_API_KEY.

---

## 16. Documentation updates

The following files must be updated alongside this one:

### MASTER_PROJECT_STATUS.md

Add to checkpoint/files table:
  EXECUTION_BRIDGE_PLAN.md | Execution bridge connecting decision engine plan to actual repo;
                             Phase A -> Phase B implementation roadmap

Update recommended next action:
  "Phase A Field/Schema Review: create FIELD_SCHEMA_REVIEW.md before any code is written"

Keep:
  Product Decision Engine planning complete / implementation not started
  YouTube setup pending owner approval
  CJ Phase 2/3 not started
  No automatic fallback connector rule

### PRODUCT_DECISION_ENGINE_PLAN.md

Add note at end of section 18 (Implementation phases) or section 21 (Final recommendation):

  "Execution bridge: see EXECUTION_BRIDGE_PLAN.md for the code-level integration
  plan connecting this design to the actual repo. Next step is Phase A Field/Schema
  Review (FIELD_SCHEMA_REVIEW.md) before any implementation begins."

### SOURCE_STRATEGY_MAP.md

In the near-term path section, add a note after Step 4 (Decision point):

  "Decision Engine: execution bridge complete (EXECUTION_BRIDGE_PLAN.md).
  Phase A Field/Schema Review is the immediate next step before any code is written.
  Source expansion rules unchanged: audit many, implement one, verify live, freeze,
  explicit owner decision."

---

## 17. Verification commands

After all files are created/updated, run:

  git status --short
  git diff -- MASTER_PROJECT_STATUS.md PRODUCT_DECISION_ENGINE_PLAN.md SOURCE_STRATEGY_MAP.md

For EXECUTION_BRIDGE_PLAN.md (new/untracked file):
  type EXECUTION_BRIDGE_PLAN.md   (Windows) or cat EXECUTION_BRIDGE_PLAN.md (Linux)

Security checks:
  grep -n "backend/.env" EXECUTION_BRIDGE_PLAN.md MASTER_PROJECT_STATUS.md PRODUCT_DECISION_ENGINE_PLAN.md SOURCE_STRATEGY_MAP.md
  (Expected: matches are documentation references only, not paths to read or write)

  grep -n "API key\|secret\|token" EXECUTION_BRIDGE_PLAN.md
  (Expected: no actual key or token values. All occurrences are variable name references.)

---

## 18. Implementation readiness summary

| Component | Status | Notes |
|---|---|---|
| backend/decision_engine.py | not created | Phase B target |
| decide_product() function signature | defined | section 4 and 5 |
| Decision output shape | defined | section 5 |
| Field mapping | complete | section 6 |
| Decision rules | complete | section 7 |
| Decision caps | complete | section 8 |
| API integration point | identified | _summary() main.py:160 |
| EXPORT_FIELDS extension | defined | section 10 |
| Frontend badge | designed | section 11 |
| Unit test scenarios | defined | section 12 |
| Risk controls | documented | section 13 |
| FIELD_SCHEMA_REVIEW.md | not created | Phase A target |
| EXECUTION_BRIDGE_PLAN.md | complete | this file |

---

## Source conversation integration note

This document integrates findings from:
- Direct code reading of backend/main.py, backend/scoring.py, backend/db.py,
  backend/sources/normalize.py, backend/sources/connectors/__init__.py
- PRODUCT_DECISION_ENGINE_PLAN.md (21-section design document)
- SOURCE_STRATEGY_MAP.md (stage definitions, source categories, decision gates)
- MASTER_PROJECT_STATUS.md (connector status and freeze rules)
- CHECKPOINT_YOUTUBE_DATA_API_AUDIT.md (YouTube setup status)
- CHECKPOINT_META_AD_LIBRARY_AUDIT.md (Meta postpone status)
- CHECKPOINT_CJ_DROPSHIPPING.md (CJ live status, Phase 2/3 roadmap)

The strategic plan defined ideal inputs (ebay_benchmark_confidence,
matching_confidence, etc.) that do not yet exist in the codebase.
This bridge narrows the Phase B scope to work only with fields that
actually exist in _summary(row) output, making Phase B immediately
implementable without any new connectors, schema changes, or API calls.
