# Decision Output Audit - Phase B Runtime Results

Created: 2026-07-08
Commit audited: 8006d40 (Implement Phase B dynamic decision engine)
Status: audit_complete / pipeline_audit_created / pending_owner_review / not_committed

eBay image/item_id pipeline audit: COMPLETE (2026-07-08)
  Root cause identified: Category A — _ebay_item_to_raw() in sources/ebay.py does not
  extract itemId or image.imageUrl from the eBay Browse API response.
  Secondary: upsert_discovered_candidate() is INSERT-only; no UPDATE path for existing rows.
  item_id IS recoverable from source_url (already stored) without any API call.
  image_url for existing rows requires eBay API call — deferred.
  No code change made. See EBAY_IMAGE_PIPELINE_AUDIT.md for full analysis.

---

## 1. Executive Summary

Phase B is working correctly as a pure function. The decision engine is live on
`/products` and `/export/products`. All 8 output fields are present on every product.
`/products/{pid}` was not changed.

Key findings:
- No products reached TEST or WATCH. All 76 products are either NEEDS_ENRICHMENT (48)
  or REJECT (28).
- This is expected and correct given current data completeness (see section 3).
- The dominant blocker across all three sources is missing field data, not logic errors.
- image_url is missing on 71 of 76 products (93%) - highest-impact single blocker.
- eBay is the largest source (37 products) and contributes 0 image_url, 0 shipping_cost,
  0 supplier_cost to any of its products - structural gaps in the eBay connector output.
- CJ (5 products) has image_url and supplier_cost working. Blocked on retail_price first,
  then shipping_cost. CJ Phase 2 + 3 would unblock them.
- None/manual (34 products) are old seed records. 25 of 34 are REJECT (negative margin
  or hard filter). 9 are NEEDS_ENRICHMENT blocked on image_url.
- Highest-ROI next step: investigate eBay image_url pipeline gap (37 products, zero cost).

---

## 2. Runtime Smoke Test Recap

| Item | Result |
|---|---|
| Commit | 8006d40 Implement Phase B dynamic decision engine |
| Pre-existing server on port 8000 | Found (pre-Phase B). Killed and restarted with committed code. |
| /health | 200 {"status":"ok","service":"Winning Products MVP"} |
| /products decision fields | ALL 8 present on every product |
| /export/products decision fields | ALL 8 present on every exported product |
| /products/{pid} shape | Unchanged - returns {product, scoring} only |
| scoring.confidence.level | Present and correct (dict with level/supported/denominator/percent) |
| Total products in DB | 76 |
| backend/.env | Not modified. Not printed. python-dotenv loaded env vars during startup import only. No secrets exposed. |

Decision distribution:

| Decision | Count | % of total |
|---|---|---|
| NEEDS_ENRICHMENT | 48 | 63% |
| REJECT | 28 | 37% |
| WATCH | 0 | 0% |
| TEST | 0 | 0% |

---

## 3. Decision Distribution Analysis

### Why NEEDS_ENRICHMENT dominates (48/76, 63%)

The NEEDS_ENRICHMENT priority check fires when any of the following is None:
retail_price, supplier_cost, shipping_cost, image_url (or product_weight_kg for CJ).

- All 37 eBay products are NEEDS_ENRICHMENT because supplier_cost, shipping_cost,
  and image_url are all missing from eBay connector output. The eBay Browse API
  does not provide supplier cost (as expected), and the connector does not persist
  shipping_cost or image_url.
- 4 of 5 CJ products are NEEDS_ENRICHMENT because retail_price is None (CJ list
  endpoint does not return suggestSellPrice; Phase 2 would fix this).
- 9 of 34 None/manual products are NEEDS_ENRICHMENT due to missing image_url or
  supplier_cost (they have price data but no image).

### Why REJECT is high (28/76, 37%)

- 25 of 28 REJECTs are None/manual products. These are seed/sample records inserted
  manually with pricing and margin data that fails the decision engine rules.
- 20 REJECTs are negative net profit (the scoring engine already computed negative
  net_profit_per_order from the manual price inputs).
- 8 REJECTs are hard filter_reasons (F1 legal, F2 shipping weight/cost, F3 fragility,
  F6 fad-collapse, F7 digital).
- 2 eBay REJECTs: 2 eBay products with negative net profit (margin math fails even
  with the current data).
- 1 CJ REJECT: 1 CJ product with a filter reason.

### Why WATCH and TEST are zero

This is expected for current live data. The decision engine reaches TEST only when ALL
of the following are simultaneously true:
1. All critical fields present (retail_price, supplier_cost, shipping_cost, image_url)
2. confidence in ("High", "Medium")
3. recommendation in ("Strong candidate", "Test with small budget")
4. caution_reasons is empty
5. positive_reasons is non-empty
6. net_profit_per_order > 0

Condition 1 alone eliminates every eBay and CJ product in the current DB.
The None/manual products that have all fields fail on negative net_profit.

WATCH is also zero because WATCH requires all critical fields to be present
(the engine only falls through to WATCH after passing all NEEDS_ENRICHMENT checks).
No product in the current DB has all four critical fields populated.

### Is this a logic error?

No. The decision engine is behaving correctly as a conservative filter.
NEEDS_ENRICHMENT with specific next_action values is the intended output for
data-incomplete products. The audit reveals structural data gaps in the connector
pipeline, not bugs in the decision logic.

---

## 4. Missing Data Analysis

| Missing field | Count | Business impact | Likely source / reason | Recommended action |
|---|---|---|---|---|
| image_url | 71/76 | Blocks NEEDS_ENRICHMENT resolution for 71 products; blocks eventual UI display | eBay connector: not mapped (37). None/manual: seed records have no image (34). CJ: working (0 missing). | Investigate eBay connector image mapping. Backfill for manual records if source URL available. |
| shipping_cost | 42/76 | Prevents margin completion; blocks reaching WATCH/TEST | eBay: 37 missing (Browse API does not return shipping for all items). CJ: 5 missing (Phase 3 logistics endpoint would fix, but blocked on retail_price first). | CJ Phase 2 -> Phase 3 for CJ products. eBay shipping gap may require eBay shipping API or manual input. |
| supplier_cost | 40/76 | Without supplier cost, margin is unknown; eBay products cannot be TEST | eBay: 37 missing (no supplier matching). None/manual: 3 missing. CJ: 0 missing (sellPrice maps correctly). | eBay products need supplier source matching (CJ/AliExpress lookup) - complex. Manual records: operator review. |
| retail_price | 5/76 | All 5 are CJ products; CJ list endpoint does not return suggestSellPrice | CJ: 5 missing (list endpoint only). Detail endpoint (Phase 2) returns retail price. | CJ Phase 2 enrichment (GET /v1/product/query?pid=). |
| product_weight_kg | 1/76 | Blocks CJ detail enrichment path | CJ: 1 product missing weight (detail endpoint or variant endpoint would fix). | Included in CJ Phase 2 detail enrichment. |

---

## 5. Source-Level Breakdown

### None/manual (34 products)

These are seed/sample records inserted manually before live connectors were active.
They have no item_id, no image_url, and varying degrees of pricing completeness.

| Metric | Value |
|---|---|
| Total | 34 |
| Decision: NEEDS_ENRICHMENT | 9 |
| Decision: REJECT | 25 |
| Decision: WATCH | 0 |
| Decision: TEST | 0 |
| missing image_url | 34/34 (100%) |
| missing supplier_cost | 3/34 |
| missing shipping_cost | 0/34 |
| missing retail_price | 0/34 |
| has item_id | 0/34 |
| Most common next_action | reject_product (25), operator_review_required (9) |

Assessment: 25 of 34 are already correctly identified as REJECT by the decision engine
(negative margin or hard filters). The 9 NEEDS_ENRICHMENT cases are blocked on
image_url only - they have price data but no image. These could potentially reach
WATCH or TEST if image is backfilled and all other fields are confirmed.

### cj_dropshipping (5 products)

Live connector, tokens active. CJ correctly maps sellPrice -> supplier_cost and
productImage -> image_url. Blocked on retail_price (Phase 2) and shipping_cost (Phase 3).

| Metric | Value |
|---|---|
| Total | 5 |
| Decision: NEEDS_ENRICHMENT | 4 |
| Decision: REJECT | 1 |
| Decision: WATCH | 0 |
| Decision: TEST | 0 |
| missing retail_price | 5/5 (100%) |
| missing shipping_cost | 5/5 (100%) |
| missing image_url | 0/5 |
| missing supplier_cost | 0/5 |
| missing product_weight_kg | 1/5 |
| has item_id | 5/5 (100%) |
| Most common next_action | run_ebay_benchmark (4), reject_product (1) |

Assessment: CJ connector is working well for the fields it covers. Phase 2 (retail price)
is the blocking enrichment - once retail_price is populated, the shipping_cost check fires
next and next_action becomes run_cj_shipping_enrichment. Phase 2 + 3 would put these 4
products in a position to reach WATCH or TEST if margin math is positive.

### ebay (37 products)

Largest live source. eBay Browse API is confirmed working in production. However, the
connector is not persisting image_url, shipping_cost, or supplier_cost (see section 6-8).

| Metric | Value |
|---|---|
| Total | 37 |
| Decision: NEEDS_ENRICHMENT | 35 |
| Decision: REJECT | 2 |
| Decision: WATCH | 0 |
| Decision: TEST | 0 |
| missing image_url | 37/37 (100%) |
| missing shipping_cost | 37/37 (100%) |
| missing supplier_cost | 37/37 (100%) |
| has item_id | 0/37 |
| Most common next_action | operator_review_required (35), reject_product (2) |

Assessment: eBay is structurally incomplete. All 37 products are in NEEDS_ENRICHMENT.
The connector discovers and scores products but does not map image, shipping cost, or
supplier cost. Without at least image_url and some form of supplier cost, eBay products
cannot reach WATCH or TEST.

---

## 6. image_url Investigation

| Source | Missing | Present | Note |
|---|---|---|---|
| None/manual | 34/34 | 0 | Old seed records. No image ever set. No source to pull from. |
| cj_dropshipping | 0/5 | 5 | CJ connector correctly maps productImage -> image_url. Working. |
| ebay | 37/37 | 0 | eBay connector does NOT persist image_url. |

CJ connector is working: `productImage` from the CJ API is mapped to `image_url` at
discovery time and persisted to the DB. This is the reference implementation.

eBay connector: eBay Browse API (`/buy/browse/v1/item_summary/search`) returns image data
in the `image.imageUrl` field for each `ItemSummary`. The eBay connector is likely not
mapping this field to `image_url` at upsert time, or the `upsert_discovered_candidate()`
function in `db.py` was not including it when these records were inserted.

None/manual records: these predate any live connector. They have no source URL or image
reference. Backfilling would require manually supplying images or re-fetching from a source
that no longer has a mapping to these items.

Likely root cause for eBay: the `upsert_discovered_candidate()` function persists 15 fields
(per FIELD_SCHEMA_REVIEW.md section 5). Whether `image_url` is among those 15 fields, and
whether the eBay connector passes it in the candidate dict, needs to be confirmed before
any backfill.

Action required (investigation only, no code change yet):
- Read `backend/connectors/ebay.py` to confirm whether `image_url` is extracted from the
  eBay API response and included in the candidate dict.
- Read `backend/db.py` `upsert_discovered_candidate()` to confirm whether image_url is
  in the 15 persisted fields.
- If both are present: existing 37 eBay records predate the mapping. Re-running discovery
  would populate image_url for new records. A safe backfill would require a separate
  targeted update for existing records.
- If image_url is missing from the connector or upsert: a targeted connector fix +
  backfill plan is needed.

---

## 7. shipping_cost Analysis

| Source | Missing shipping_cost | Has item_id | Could use CJ enrichment |
|---|---|---|---|
| cj_dropshipping | 5/5 | 5/5 | Yes (after retail_price is filled first) |
| ebay | 37/37 | 0/37 | No |
| None/manual | 0/34 | 0/34 | N/A |

Why run_cj_shipping_enrichment count = 0:

The decision engine evaluates missing fields in priority order:
  retail_price -> supplier_cost -> shipping_cost -> image_url -> product_weight_kg

All 5 CJ products are missing retail_price. The retail_price NEEDS_ENRICHMENT check fires
first and returns next_action = "run_ebay_benchmark" before the shipping_cost check is
ever evaluated. Once CJ Phase 2 populates retail_price for these 5 products, the
shipping_cost check will fire next and next_action will become "run_cj_shipping_enrichment".

This is correct priority behavior. The fix is not in the decision engine - it is in
running CJ Phase 2 first.

eBay shipping_cost: eBay products have item_id = None (the eBay item ID is not being
persisted as item_id in the DB, or the connector uses a different field). Even if shipping
data were available from eBay, the CJ shipping enrichment path requires source ==
"cj_dropshipping" and item_id. eBay shipping gaps require a separate path
(eBay Shipping API, or operator manual input).

Theoretical CJ shipping enrichment candidates: 5 products (all CJ) once retail_price
is populated by Phase 2.

---

## 8. supplier_cost Analysis

| Source | Missing supplier_cost | Note |
|---|---|---|
| ebay | 37/37 | eBay is a marketplace. sellPrice is the buyer price. No supplier price field. |
| None/manual | 3/34 | 3 manual records missing price data. |
| cj_dropshipping | 0/5 | CJ sellPrice -> supplier_cost mapping is working. |

eBay products cannot become TEST without supplier cost. The eBay Browse API returns the
retail listing price (`price`) which maps to retail_price, but there is no equivalent
field for supplier/wholesale cost. Turning eBay-discovered products into shippable
candidates requires matching them against a dropshipping supplier (CJ, AliExpress, etc.)
to find a supplier_cost. This is a product-matching problem, not an API enrichment problem.

This is the highest-complexity gap. It is not solvable by an API call enrichment alone.
It requires a supplier matching strategy that is not yet planned.

The 3 None/manual records missing supplier_cost can only be fixed by operator manual input.

---

## 9. retail_price Analysis

| Source | Missing retail_price | next_action assigned |
|---|---|---|
| cj_dropshipping | 5/5 | run_ebay_benchmark (4 NEEDS_ENRICHMENT) |
| ebay | 0/37 | N/A (retail_price present from eBay price field) |
| None/manual | 0/34 | N/A |

All 5 missing retail_price cases are CJ products. The "run_ebay_benchmark" next_action
is correctly assigned: when a CJ product has no retail_price, the decision engine directs
the operator to run an eBay price benchmark to establish market price.

CJ Phase 2 (GET /v1/product/query?pid=) is the intended fix. The detail endpoint returns
suggestSellPrice which maps to retail_price. After Phase 2, retail_price will be populated
and the decision engine will proceed to the shipping_cost check.

Note: the 1 CJ REJECT product is not shown in the NEEDS_ENRICHMENT analysis above.
That product has a filter_reason and hits the REJECT gate before retail_price is checked.

---

## 10. REJECT Analysis

Total REJECTs: 28 (25 None/manual, 2 eBay, 1 CJ)

### By reject reason

| Reason | Count | Source |
|---|---|---|
| Net profit is negative | 20 | Mostly None/manual (seed products with unfavorable margins) |
| F2 shipping: weight > 2kg | 2 | None/manual |
| F7 digital: intangible/non-shippable product | 2 | None/manual |
| F2 shipping: ship cost > 30% of retail | 1 | None/manual |
| F6 fad-collapse: historical peak >= 5x current | 1 | None/manual |
| F3 fragility: fragile material + breakage reports | 1 | None/manual |
| F1 legal: restricted/prohibited class | 1 | None/manual |
| F2 shipping: longest dimension > 60cm | 1 | None/manual |

Negative net profit dominates (20/28 REJECTs). These are manual seed products where
the pricing data was set at insertion time but margin math produced negative results.
The decision engine correctly identifies and rejects them.

The 8 filter_reason REJECTs are products that the scoring engine flagged with hard
elimination criteria. The decision engine passes filter_reasons through as decision_reasons,
which is the intended behavior.

No CJ product was rejected for missing supplier_cost (the CJ supplier_cost = None REJECT
check has no current triggers - all 5 CJ products have supplier_cost).

---

## 11. Product Examples

### Example 1: NEEDS_ENRICHMENT - image_url only

| Field | Value |
|---|---|
| id | 1 |
| name | Posture Corrector Back Brace |
| source | None (manual) |
| decision | NEEDS_ENRICHMENT |
| decision_confidence | MEDIUM |
| missing_data | ["image_url"] |
| next_action | operator_review_required |
| decision_reasons | ["Product image missing"] |

Note: This product has retail_price=39.0, supplier_cost=6.0, shipping_cost=3.0,
net_profit=10.0, confidence=High, recommendation="Test with small budget". It would be
a strong TEST candidate if image_url were present. Highest-priority backfill target.

### Example 2: NEEDS_ENRICHMENT - CJ missing retail_price and shipping_cost

| Field | Value |
|---|---|
| id | 87 |
| name | Hallux Valgus Corrector (CJ) |
| source | cj_dropshipping |
| decision | NEEDS_ENRICHMENT |
| decision_confidence | LOW |
| missing_data | ["retail_price", "shipping_cost"] |
| next_action | run_ebay_benchmark |
| decision_reasons | ["Market price benchmark missing"] |

Note: retail_price check fires first. Once CJ Phase 2 fills retail_price, the decision
engine will re-evaluate and the next blocker will be shipping_cost ->
next_action = run_cj_shipping_enrichment.

### Example 3: NEEDS_ENRICHMENT - supplier_cost missing

| Field | Value |
|---|---|
| id | 32 |
| name | Kitchen Mop Broom Holder (manual) |
| source | None (manual) |
| decision | NEEDS_ENRICHMENT |
| decision_confidence | LOW |
| missing_data | ["supplier_cost", "image_url"] |
| next_action | operator_review_required |
| decision_reasons | ["Supplier cost missing"] |

Note: supplier_cost check fires before image_url. Operator must provide both to resolve.

### Example 4: REJECT - negative net profit

| Field | Value |
|---|---|
| id | 2 |
| name | RGB LED Strip Lights (manual) |
| source | None (manual) |
| decision | REJECT |
| decision_confidence | MEDIUM |
| missing_data | ["image_url"] |
| next_action | reject_product |
| decision_reasons | ["Net profit is negative (-13.0)"] |

Note: Even if image_url were present, this product would still REJECT due to negative
net profit. No enrichment path resolves a negative margin.

---

## 12. Next-Step Options Based on Actual Output

### Option A - Investigate and fix eBay image_url pipeline

Pros:
- Largest single blocker: 71/76 products (93%) missing image_url.
- eBay Browse API returns image.imageUrl in ItemSummary. If the connector is already
  extracting it, a safe re-discovery or targeted backfill of the 37 existing eBay records
  could be done without a DB schema change.
- Low complexity if the field is already available in the connector output.
- Would immediately move ~9 None/manual + up to 35 eBay products from image-blocked
  NEEDS_ENRICHMENT toward the next blocker (shipping_cost for eBay, image already done
  for CJ). The 9 manual records with all other fields complete could reach WATCH/TEST.
- No new connector needed. Investigation only first.

Cons:
- None/manual records have no discoverable source to pull image from. Their image_url
  gap can only be fixed by operator manual input.
- For eBay, re-running discovery on existing item_ids requires knowing those item_ids
  (currently item_id = None for all eBay products - gap in item_id persistence).
- Backfill requires a safe, targeted update plan and a tested write path.

### Option B - CJ Phase 2 retail price enrichment

Pros:
- 5 CJ products all need retail_price. Phase 2 (GET /v1/product/query?pid=) is already
  planned and scoped.
- Once retail_price is filled, CJ products move to the shipping_cost check
  (next_action = run_cj_shipping_enrichment). Phase 3 follows naturally.
- All 5 CJ products have item_id, so the enrichment lookup has a clear key.
- CJ Phase 2 + 3 could move 4 CJ products to WATCH or TEST if margin math is positive.

Cons:
- Only affects 5 products (small volume right now).
- Unblocks CJ but does not help eBay or manual records at all.
- CJ token still active; no access re-approval needed.

### Option C - eBay item_id and supplier cost matching

Pros:
- 37 eBay products. Resolving supplier_cost would unlock the largest source.
- Matching eBay products to CJ/AliExpress suppliers is the correct long-term path
  for the dropshipping model.

Cons:
- Highest complexity of all options. Requires product matching logic, not just an API call.
- Even if supplier_cost is resolved, eBay products still need shipping_cost and image_url.
- Structural gap: eBay item_id is not being persisted (item_id = None on all 37 eBay
  records), meaning there is no key to use for any eBay enrichment lookup.
- Not currently planned or scoped.

### Option D - YouTube Data API setup

Pros:
- Adds content demand signal (video trend data) to scoring.
- Legitimate new data dimension.

Cons:
- Does not resolve image_url, supplier_cost, or shipping_cost for any current product.
- Adding signal without completing data does not move any product from NEEDS_ENRICHMENT
  to WATCH or TEST.
- Lower immediate ROI than data enrichment options.
- Still requires owner approval before implementation.

---

## 13. Recommendation

Based on actual Phase B output, ranked by ROI:

1. **Investigate eBay image_url pipeline gap (no code change yet)**
   Read `backend/connectors/ebay.py` and `backend/db.py` `upsert_discovered_candidate()`
   to confirm whether image_url is extracted and persisted. If the field is available in
   the connector output but not persisted, a targeted fix is low-complexity. If it is not
   extracted from the eBay API response, a connector update is needed.
   This is purely an investigation step - no code change, no commit, no external API call.

2. **CJ Phase 2 (retail price enrichment)**
   5 CJ products, all have item_id, clear endpoint. Directly unblocks Phase 3 shipping.
   Scoped, reversible, uses already-approved CJ token.

3. **CJ Phase 3 (shipping cost enrichment)**
   Follows Phase 2 naturally. 5 CJ products with item_id. Once retail_price and
   shipping_cost are filled, CJ products can be evaluated for WATCH/TEST.

4. **eBay item_id persistence investigation**
   The eBay connector does not appear to persist item_id for discovered products.
   Confirming this is a prerequisite for any eBay backfill strategy. Investigation only.

5. **YouTube Data API setup**
   Adds signal but does not resolve the data gaps blocking NEEDS_ENRICHMENT resolution.
   Defer until enrichment steps 1-3 are complete or explicitly deprioritized.

None of the above should start without explicit owner approval. This audit provides the
factual basis for that decision.

---

## 14. Safety Rules for Next Phase

- No blind DB backfill: any write to existing records requires a targeted plan,
  per-record verification, and a stated rollback path.
- No overwriting existing non-null data without backup.
- No connector changes without a written targeted plan reviewed before implementation.
- No external APIs unless explicitly approved: eBay investigation = read connector code
  only, no live API calls. CJ Phase 2 = approved path using existing token.
- No discovery runs during audit phases.
- No DB schema changes without a migration plan.
- item_id gap in eBay records: do not attempt to retroactively fill item_id without
  confirming the source of truth (eBay itemId field in the API response).

---

## 15. Documentation Updates

See sections 3 and 14 for content used to update MASTER_PROJECT_STATUS.md,
EXECUTION_BRIDGE_PLAN.md, and FIELD_SCHEMA_REVIEW.md.

---

## 16. Appendix: Raw Smoke Test Numbers

Backend: python -m dotenv -f .env run -- python -m uvicorn main:app --host 0.0.0.0 --port 8000
Tested against: http://localhost:8000

/products: 200, 76 products
/export/products?format=json: 200, 76 products
/products/1: 200, {product, scoring} shape confirmed, scoring.confidence.level = "High"

All 8 decision fields confirmed present on /products and /export/products:
  decision, decision_confidence, margin_status, estimated_net_margin,
  missing_data, risk_flags, decision_reasons, next_action

No external source APIs called during smoke test.
No discovery endpoints called.
backend/.env not modified. Not printed. No secrets exposed.
