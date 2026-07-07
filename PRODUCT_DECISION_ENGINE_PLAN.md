# Product Decision Engine Plan

Last updated: 2026-07-07
Status: planning_complete / implementation_not_started

Execution bridge: EXECUTION_BRIDGE_PLAN.md maps this design to the actual repo
(backend/main.py, backend/scoring.py, backend/db.py). It defines the exact
integration points, field mapping, Phase B decision rules using only existing
fields, and an implementation checklist. Read the bridge before writing any code.

Phase A Field/Schema Review: COMPLETE / pending owner review.
  FIELD_SCHEMA_REVIEW.md created. Read it before Phase B implementation.
  Phase B must only use fields confirmed available in FIELD_SCHEMA_REVIEW.md section 7.
  Fields NOT available for Phase B are listed in FIELD_SCHEMA_REVIEW.md section 11.
  Phase B requires no DB migration. Next step: backend/decision_engine.py with decide_product().

---

## 1. Executive summary

The MVP currently collects real product data from live sources: CJ Dropshipping provides supplier cost,
weight, and image; eBay provides market price benchmarks and competition signals. Data is normalized,
scored, and saved to the database. Operators can export products.

The missing layer is product decision logic.

A raw score tells you a product looks interesting. A decision tells you what to do next.

The Product Decision Engine is the system that evaluates each collected product and produces:

- A decision: TEST, WATCH, NEEDS_ENRICHMENT, or REJECT
- A confidence level: HIGH, MEDIUM, or LOW
- A set of reasons explaining why
- A list of missing data that must be resolved
- A concrete next action for the operator

The engine must be explainable. Operators must be able to read why a product was selected or rejected
without interpreting raw numeric scores. This is the difference between a data tool and a product
selection assistant.

---

## 2. Current problem

### What exists today

- eBay is live and closed. It returns listing prices, competition counts, and search results for product
  keywords. It is a market benchmark and retail price estimator.
- CJ Dropshipping is live and closed. It returns supplier cost (sellPrice), product weight, image URL,
  and product category. Retail price is not available from the list endpoint.
- TikTok Commercial Content API: pending access. No data yet.
- Google Trends API: pending alpha invitation. No data yet.
- YouTube Data API: audit complete, suitability decision = proceed_to_setup, setup pending owner approval. Not implemented.
- Meta Ad Library: audit complete, postponed. Not approved.

### What is missing

Current scoring produces a numeric score. The score reflects completeness and basic profitability
signals but does not produce a business decision.

Problems:
- A product with a high score may still be rejected for risk reasons (brand risk, restricted category,
  unknown shipping).
- A product with a medium score may still be a strong TEST candidate if margin is clear and risk is low.
- Operators have no structured way to know why a product scored high or low.
- Missing data (e.g., shipping cost) is not surfaced as a blocker.
- The system does not distinguish: "this product needs more data" from "this product should be rejected."

### What the decision engine provides

For every evaluated product, the engine outputs:

  decision:          TEST | WATCH | NEEDS_ENRICHMENT | REJECT
  confidence:        HIGH | MEDIUM | LOW
  decision_reasons:  list of strings explaining the decision
  missing_data:      list of fields that are absent and affecting the decision
  risk_flags:        list of identified risk signals
  next_action:       the concrete action the operator should take

---

## 3. Product lifecycle

Every product in the system moves through the following stages:

  discovered         Product found by a source connector (CJ, eBay, etc.). Raw data only.

  normalized         Product fields mapped to standard schema via normalize_candidate().
                     Title cleaned, category set, source fields mapped.

  matched            Product from one source (e.g., CJ) has been compared against another
                     source (e.g., eBay) for price/demand benchmarking.
                     Matching confidence recorded.

  enriched           Additional fields added beyond initial discovery:
                     - Phase 2: CJ detail endpoint adds retail price suggestion
                     - Phase 3: CJ shipping endpoint adds shipping cost
                     - Future: demand signals from TikTok, Google Trends, YouTube

  evaluated          Decision engine has run. decision, confidence, reasons, missing_data,
                     risk_flags, and next_action are all set.

  shortlisted        Operator has reviewed evaluated product and marked it as worth
                     further attention. Pre-test review step.

  test_candidate     Operator has approved a small test campaign or offer preparation.
                     Product is ready for live test.

  tested             Test has been run. Performance data recorded.
                     (ad_spend, impressions, clicks, ctr, purchases, revenue, roas)

  winner             Product passed the test threshold. Moved to active catalog.

  rejected           Product failed at some lifecycle stage: evaluation, test, or operator review.
                     Hard rejections are permanent. Soft rejections may be reconsidered with
                     new evidence.

Transitions:
- discovered -> normalized:      automatic, on data ingestion
- normalized -> matched:         triggered by eBay benchmark lookup (manual or scheduled)
- matched -> enriched:           triggered by CJ Phase 2/3 (when approved and implemented)
- enriched -> evaluated:         triggered by decision engine run
- evaluated -> shortlisted:      operator manual action in dashboard
- shortlisted -> test_candidate: operator explicit approval
- test_candidate -> tested:      test campaign executed, results recorded
- tested -> winner/rejected:     outcome of test evaluation

---

## 4. Final decision statuses

### TEST

Enough evidence exists to run a small test. The product has:
- Confirmed supplier cost
- Estimated retail benchmark with medium or high confidence
- Positive estimated margin (after cost, shipping, fees)
- At least one demand signal (eBay listing evidence, or future ad/content signal)
- No hard risk flags

Next action: prepare_test_offer

Operator instruction: Create an offer page or test ad campaign for this product. Budget cap $50-$200.

### WATCH

The product is promising but not yet ready for a test decision. Either:
- Demand signal exists but margin or shipping is unclear
- Margin exists but demand evidence is insufficient
- Matching confidence is medium and retail benchmark is weak

Next action: monitor, wait for additional signals (TikTok, Google Trends), or schedule enrichment

Operator instruction: Add to watchlist. Revisit after pending signal sources are active
or after enrichment is completed.

### NEEDS_ENRICHMENT

The product has potential but is missing at least one critical field needed for a decision.

Common triggers:
- shipping_cost is None (unable to compute net margin)
- retail benchmark is absent or low confidence (cannot confirm margin exists)
- supplier-to-market matching confidence is low
- image is missing (cannot prepare offer)
- variant/weight data is missing for shipping calculation

Next action: run the specific enrichment step that resolves the missing field.

Operator instruction: This product cannot be decided yet. Run the named enrichment step
and re-evaluate. Do not add to test queue.

### REJECT

The product should not be tested. Hard conditions include:
- Estimated margin is negative
- Restricted or regulated category
- Clear brand/trademark risk
- Medical or health claims risk
- No supplier availability
- No market benchmark evidence
- Duplicate of an already-rejected product
- Supplier cost is equal to or above market benchmark

Next action: reject_product

Operator instruction: Do not test. Mark as rejected. If new information appears
(e.g., found a cheaper supplier, category classification changes), a new evaluation
can be triggered.

---

## 5. Decision inputs

### Core identity

  normalized_title           Cleaned product title after normalization
  source                     Source connector name (cj_dropshipping, ebay, etc.)
  source_item_id             Unique ID from source (CJ pid, eBay item ID)
  source_url                 Link to original listing (may be None)
  image_url                  Product image URL
  category                   Normalized product category string
  country                    Target market country (default: US)

### Supplier data

  supplier_cost              Price the dropshipper pays per unit (CJ sellPrice)
  product_weight_kg          Product weight in kg (from CJ productWeight / 1000)
  product_dimensions         Length x width x height (future CJ variant endpoint)
  supplier_availability      Boolean or count indicating stock status
  variant_count              Number of variants available
  cj_pid                     CJ product ID (for Phase 2/3 enrichment)
  cj_vid                     CJ variant ID (for Phase 3 shipping calculation)

### Market benchmark (from eBay)

  ebay_avg_price             Average price of similar eBay listings
  ebay_median_price          Median price of similar eBay listings
  ebay_min_price             Minimum observed listing price
  ebay_max_price             Maximum observed listing price
  ebay_listing_count         Number of listings found for the product keyword
  ebay_similar_items_count   Subset count: listings that are genuinely similar
  ebay_benchmark_confidence  low | medium | high

### Profitability

  estimated_retail_price     Best estimate of what this product sells for at retail
                             (from ebay_median_price or CJ suggestSellPrice if available)
  supplier_cost              (same as above)
  shipping_cost              Cost to ship one unit to customer (from CJ Phase 3 or estimate)
  estimated_fees             Platform fees, payment processing (% of retail, estimated)
  estimated_cac              Customer acquisition cost estimate (ad spend / conversion assumed)
  estimated_net_margin       = estimated_retail_price - supplier_cost - shipping_cost
                               - estimated_fees - estimated_cac
  margin_status              strong_margin | acceptable_margin | weak_margin |
                             unknown_margin | negative_margin

### Demand evidence

  ebay_demand_evidence       Boolean + signal: listing count and competition level
  future_tiktok_ad_signal    Pending: will provide ad creative count + engagement range
  future_google_trends_signal Pending: will provide search interest score + trend direction
  future_youtube_content_signal Pending: will provide video count + top view count
  future_reddit_pain_signal  Pending: will provide subreddit activity + pain signal

### Risk

  restricted_category_risk   Boolean: product is in a regulated category
  branded_counterfeit_risk   Boolean: product title or image suggests brand/trademark
  medical_claims_risk        Boolean: product implies medical or health benefit
  fragile_risk               Boolean: product is fragile and high breakage risk
  battery_risk               Boolean: product contains battery (shipping compliance)
  heavy_shipping_risk        Boolean: product weight exceeds threshold for standard shipping
  compliance_notes           Free text: any identified compliance concerns

### Output fields

  decision                   TEST | WATCH | NEEDS_ENRICHMENT | REJECT
  confidence                 HIGH | MEDIUM | LOW
  decision_reasons           List of strings: why this decision was made
  missing_data               List of field names: what is absent and affecting the decision
  risk_flags                 List of identified risk signals
  next_action                Single action code (see section 15)

---

## 6. Evidence model

Evidence is the structured set of observations that support or block a decision.
Evidence should be stored as named fields or JSON alongside the product record.
Do not mix raw data with evidence interpretation.

### supplier_evidence

Confirms that the product can actually be sourced and dropped shipped.

Required to produce: supplier_cost, image_url, product_weight_kg
Future fields: variant_count, supplier_availability, cj_vid

Without supplier_evidence: product cannot be evaluated. Assign REJECT or skip.

### market_price_evidence

Confirms that a retail price exists and can be estimated.

Source: eBay benchmark lookup
Required to produce: ebay_avg_price, ebay_median_price, ebay_listing_count,
                     ebay_benchmark_confidence, estimated_retail_price

Without market_price_evidence: margin cannot be computed. Assign NEEDS_ENRICHMENT
if supplier data exists, REJECT if no supplier data either.

### demand_evidence

Confirms that buyers are interested in this product type.

Currently available: eBay listing count + competition as a proxy
Future: TikTok ad count, Google Trends score, YouTube video count, Reddit post count

Low demand_evidence does not automatically REJECT. It may lower confidence or
prevent a TEST decision until signal strengthens.

### ad_evidence

Confirms that sellers are actively paying to advertise this product.

Source: TikTok Commercial Content API (pending approval)
Signals: ad creative count, engagement range, advertiser page count, active ad status

High ad_evidence raises confidence significantly: if others are spending on ads, demand is proven.
Without ad_evidence: cannot confirm paid demand. Does not block decision alone.

### content_evidence

Confirms that creators and reviewers are covering this product.

Source: YouTube Data API (audit complete, pending setup approval)
Signals: total video count for keyword, view counts on top videos, content velocity
         (videos published in last 90 days), unboxing/review/comparison video presence

High content_evidence raises WATCH -> TEST confidence.
Without content_evidence: does not block decision. Missing signal only, not blocking.

### risk_evidence

Warns about conditions that may block the product from being tested safely.

Signals: restricted_category_risk, branded_counterfeit_risk, medical_claims_risk,
         fragile_risk, battery_risk, heavy_shipping_risk, compliance_notes

Any HIGH risk flag triggers a review. Some risk flags trigger automatic REJECT
(see hard rejection rules in section 11).

Risk evidence should be generated during normalization or enrichment, not manually.

---

## 7. eBay role in the decision engine

eBay serves four distinct functions:

### Function 1 - Market benchmark

eBay provides the most accessible real-world retail price data for physical consumer products.
When a CJ product keyword is searched on eBay, the resulting listing prices form a benchmark:
what real buyers are currently paying for the same or similar item.

### Function 2 - Retail price estimator

The median eBay listing price for a product keyword becomes estimated_retail_price.
This is the baseline for margin calculation.

Priority order for estimated_retail_price:
1. eBay median price (if listing count >= threshold and confidence >= medium)
2. CJ suggestSellPrice lower bound (if available from Phase 2 enrichment)
3. Not estimatable -> NEEDS_ENRICHMENT

### Function 3 - Competition signal

The number of active eBay listings for a product keyword indicates market saturation:
- High listing count + low median price = saturated, margin compressed
- Low listing count + higher prices = underserved, opportunity
- Zero listings = no market evidence on eBay (may need alternative benchmark)

### Function 4 - Demand proxy

eBay listing count, sell-through indicators, and price clustering serve as a proxy
for buyer demand in the absence of TikTok or Google Trends data.

### eBay benchmark computation rules

  Input:  product keyword (from normalized_title)
  Search: eBay Browse API with keyword, country=US
  Collect: itemSummaries list
  Compute:
    - listing_prices = [item.price.value for item in results]
    - ebay_avg_price = mean(listing_prices)
    - ebay_median_price = median(listing_prices)
    - ebay_min_price = min(listing_prices)
    - ebay_max_price = max(listing_prices)
    - ebay_listing_count = len(results)

  Confidence rules:
    - listing_count >= 20 AND price_variance low -> HIGH
    - listing_count 5-19 OR price_variance medium -> MEDIUM
    - listing_count < 5 OR price_variance high -> LOW

  If ebay_benchmark_confidence = LOW:
    - estimated_retail_price marked unreliable
    - margin calculation should not produce TEST decision
    - decision may be NEEDS_ENRICHMENT or WATCH

### eBay benchmark rejection threshold

If listing_count < 3: no benchmark. Mark market_price_evidence as absent.
Decision falls to NEEDS_ENRICHMENT or REJECT depending on other signals.

---

## 8. CJ role in the decision engine

CJ Dropshipping serves five functions:

### Function 1 - Supplier source

CJ confirms the product is available to dropship. Without a CJ product record,
the product has no supplier and cannot be tested.

### Function 2 - Cost source

CJ sellPrice = supplier_cost. This is the floor cost per unit. No margin
calculation is possible without it.

### Function 3 - Image source

CJ productImage = image_url. Without an image, offer preparation is not possible.
Missing image -> NEEDS_ENRICHMENT at minimum, may block TEST.

### Function 4 - Weight source

CJ productWeight / 1000 = product_weight_kg. Weight is required to estimate
shipping cost ranges. Without weight, shipping estimation is unreliable.

### Function 5 - Future enrichment source (Phase 2 and Phase 3)

Phase 2 (not yet implemented):
  - Endpoint: GET /v1/product/query?pid={pid}
  - Adds: suggestSellPrice (retail price suggestion as a range string)
  - Benefit: fills estimated_retail_price if eBay benchmark is weak

Phase 3 (not yet implemented):
  - Flow: GET /v1/product/variant/query?pid={pid} -> cj_vid
          POST /v1/logistic/freightCalculate with vid + destination
  - Adds: shipping_cost (actual logistics cost for one unit, US destination)
  - Benefit: enables accurate net margin calculation

### CJ current limitations and their decision impact

  retail_price = None in live mode:
    If eBay benchmark is also absent or low confidence,
    estimated_retail_price is unknown -> margin_status = unknown_margin
    -> decision cannot be TEST

  shipping_cost = None (Phase 3 not done):
    Net margin formula is incomplete
    -> decision = NEEDS_ENRICHMENT for most products
    -> exception: if product is very lightweight (<0.3kg) and margin is
       obviously strong even with a shipping estimate, may allow WATCH

  source_url = None (CJ does not return product URL):
    Offer preparation must use image_url alone
    -> not a blocker but noted in missing_data

### Decision impact summary for CJ Phase 2 and Phase 3

Until Phase 3 shipping enrichment is complete, most products with unknown
shipping cost should be NEEDS_ENRICHMENT, not TEST.

Exception: products with weight < 0.3 kg may allow an estimated flat-rate
shipping assumption ($3-5 USD epacket), and if margin is still strong even
at that assumption, may be upgraded to WATCH.

The decision model should make Phase 2 and Phase 3 dependency explicit in
missing_data and next_action outputs.

---

## 9. eBay-to-CJ matching logic

Matching is the process of determining whether a CJ product and an eBay listing
(or set of listings) represent the same product for benchmarking purposes.

Incorrect matching is one of the highest-risk failure modes in the decision engine.
If a CJ generic phone case is matched against an Apple-branded case on eBay, the
retail benchmark will be inflated and the margin will appear larger than it is.

### Matching inputs

  cj_title           Product name from CJ (e.g., "Adjustable Posture Corrector Back Support")
  cj_category        Category from CJ (e.g., "Health & Beauty")
  cj_price           Supplier cost (floor for comparison)
  ebay_title         Title from eBay search result
  ebay_category      eBay category
  ebay_price         Listed retail price
  image_available    Whether CJ image can be used for visual comparison (future)

### Matching levels

  exact_keyword_match
    The core non-branded keywords of the CJ title appear in the eBay title in the
    same order or combination.
    Example: "posture corrector" in both titles.
    Confidence: HIGH (if no brand conflict)

  strong_title_similarity
    Most content words match. Minor variations in wording.
    Example: "back posture corrector brace" vs "posture corrector back brace support"
    Confidence: MEDIUM to HIGH

  partial_match
    Some keywords match but significant words differ.
    May indicate a similar but not identical product.
    Example: "posture corrector" vs "posture support pillow"
    Confidence: LOW to MEDIUM

  weak_match
    Only category or broad theme matches. Product may be different.
    Example: "back support" vs "lumbar cushion"
    Confidence: LOW

  no_match
    No meaningful shared keywords. Products are different.
    Confidence: NONE - do not use as benchmark

### Matching rules

Rule 1: Do not assume products are the same from title similarity alone.
  A title match without price proximity is suspicious.
  If CJ price is $4 and eBay median is $8, check if it is plausible that CJ
  is the supplier for those eBay listings.
  If CJ price is $4 and eBay median is $80, something is wrong: mismatch or
  wrong product category.

Rule 2: Reject brand-contaminated matches.
  If the eBay title contains a brand name not present in the CJ title,
  downgrade confidence to LOW or NO_MATCH.
  Example: CJ "posture corrector" matched against eBay "Fivalifitness Posture Corrector"
  -> branded eBay listings should be excluded from the benchmark median.

Rule 3: Match confidence flows into decision confidence.
  If matching_confidence = LOW -> ebay_benchmark_confidence = LOW
  -> margin_status = unknown_margin or unreliable
  -> decision = NEEDS_ENRICHMENT or WATCH (never TEST)

Rule 4: Brand/trademark risk check during matching.
  If the CJ product title or category matches known brand patterns
  (detected by keyword lists or category rules), flag branded_counterfeit_risk = True
  and assign REJECT regardless of margin.

### eBay benchmark query strategy

To improve matching quality:
1. Use only the most specific non-branded keywords from normalized_title as the search query.
2. Filter eBay results: price within 3x of CJ supplier cost (e.g., if supplier cost is $8,
   focus on eBay listings $8-$60). Exclude extreme outliers.
3. Count how many filtered results pass the brand check.
4. Use filtered list for price statistics.
5. If filtered list is too small (< 3 items), lower benchmark confidence to LOW.

---

## 10. Profitability model

### Net margin formula

  estimated_net_margin =
      estimated_retail_price
    - supplier_cost
    - shipping_cost
    - estimated_fees
    - estimated_cac

### Field definitions

  estimated_retail_price   Median eBay listing price for the matched product keyword
                           (or CJ suggestSellPrice lower bound from Phase 2)

  supplier_cost            CJ sellPrice (confirmed live)

  shipping_cost            Actual shipping cost from CJ logistics (Phase 3)
                           or estimated flat rate if weight known and Phase 3 not done

  estimated_fees           Platform/payment fees: typically 10-15% of retail price
                           Default assumption if not configured: 13% of estimated_retail_price

  estimated_cac            Cost to acquire one customer via paid ads
                           Default assumption if not configured: $8-15 USD
                           (Conservative estimate for DTC/dropshipping)

### Margin status thresholds

  strong_margin     net_margin >= 35% of estimated_retail_price
  acceptable_margin net_margin 20-34% of estimated_retail_price
  weak_margin       net_margin 10-19% of estimated_retail_price
  unknown_margin    any required field is missing (cannot compute)
  negative_margin   net_margin < 0 (REJECT condition)

### Decision rules based on margin status

  strong_margin + low risk + demand evidence       -> TEST (HIGH confidence)
  acceptable_margin + low risk + demand evidence   -> TEST (MEDIUM confidence)
  weak_margin + low risk + demand evidence         -> WATCH (MEDIUM confidence)
  unknown_margin                                   -> NEEDS_ENRICHMENT
  negative_margin                                  -> REJECT (hard rule)

### Handling missing fields

  supplier_cost missing:
    If source is CJ: REJECT (CJ should always provide cost; missing means bad data)
    If source is other: NEEDS_ENRICHMENT

  shipping_cost missing:
    Typical case: CJ Phase 3 not yet run
    If product_weight_kg < 0.3: may use estimated flat-rate shipping ($4 USD assumption)
      -> if margin still strong with estimate: WATCH (not TEST)
      -> decision_reasons should note "shipping_cost estimated, not confirmed"
    If product_weight_kg >= 0.3 or missing: NEEDS_ENRICHMENT
      next_action: run_cj_shipping_enrichment

  estimated_retail_price missing:
    eBay benchmark absent AND CJ Phase 2 not run
    -> NEEDS_ENRICHMENT
    next_action: run_ebay_benchmark (or run_cj_detail_enrichment for Phase 2)

  estimated_fees assumption:
    If not configured, default to 13% of estimated_retail_price
    Flag in decision_reasons: "fees are estimated at 13%, not confirmed"

  estimated_cac assumption:
    Default: $10 USD per customer acquired (conservative for dropshipping)
    Flag in decision_reasons: "CAC is a default estimate, not measured from real campaigns"

---

## 11. Hard rejection rules

The following conditions always produce REJECT regardless of score or margin.
These rules run before scoring and override all other logic.

  RULE-01: Restricted or regulated product
    Any product in a restricted category (weapons, controlled substances,
    prescription-only items, medical devices requiring clearance)
    -> restricted_category_risk = True -> REJECT

  RULE-02: Brand/trademark risk
    Product title, description, or image suggests a real brand trademark
    (e.g., product says "Nike", "Apple", "Disney", contains registered brand logo)
    -> branded_counterfeit_risk = True -> REJECT

  RULE-03: Medical or health claims risk
    Product description implies medical treatment, cure, or diagnosis
    (e.g., "treats arthritis", "FDA-approved", "medical device", "clinical")
    -> medical_claims_risk = True -> REJECT
    Exception: generic wellness products with no specific health claims may be WATCH
    with operator_review_required flag.

  RULE-04: Adult or unsafe products
    Product is clearly adult-only, unsafe, or violates platform policies
    -> REJECT

  RULE-05: Heavy product with unknown shipping
    product_weight_kg > 2.0 AND shipping_cost is None
    Estimated shipping on heavy items is unreliable and often makes margins negative.
    -> REJECT or NEEDS_ENRICHMENT (run_cj_shipping_enrichment)
    Prefer NEEDS_ENRICHMENT if product otherwise looks promising.

  RULE-06: Battery or electronics compliance risk
    Product contains lithium battery or requires CE/FCC/UL certification
    and compliance_notes are absent
    -> battery_risk = True -> REJECT (pending compliance review)
    Exception: if operator confirms compliance, flag can be cleared manually.

  RULE-07: Fragile product with high breakage risk
    Product is highly fragile (glass, ceramics, complex electronics)
    and packaging quality is unknown
    -> fragile_risk = True -> REJECT or WATCH with operator_review_required

  RULE-08: Negative estimated margin
    estimated_net_margin < 0
    -> negative_margin -> REJECT (hard)

  RULE-09: Supplier cost at or above market benchmark
    supplier_cost >= estimated_retail_price
    No room for margin exists.
    -> REJECT

  RULE-10: No image
    image_url is None or empty
    Cannot prepare an offer without an image.
    -> NEEDS_ENRICHMENT (minor) or if consistently missing across all variants: REJECT

  RULE-11: No supplier availability
    supplier_availability = False or stock = 0
    Cannot source and fulfill.
    -> REJECT

  RULE-12: No market evidence on eBay
    ebay_listing_count < 3 AND no other demand signal exists
    Market does not exist or is too niche to benchmark.
    -> NEEDS_ENRICHMENT or WATCH (if other signals exist in future)

  RULE-13: Obvious duplicate
    A product with the same source_item_id already exists in DB and was previously rejected.
    -> REJECT (auto, no re-evaluation)

  RULE-14: Currency or country mismatch
    Product price is in a currency other than the target market currency and no
    conversion is available.
    -> NEEDS_ENRICHMENT or flag for operator review.

---

## 12. Confidence model

### HIGH confidence

All of the following are true:
- supplier_cost is present and > 0
- ebay_benchmark_confidence is MEDIUM or HIGH
- margin_status is strong_margin or acceptable_margin
- No hard risk flags are set
- At least one demand signal exists:
  - eBay listing count >= 10, OR
  - Future: TikTok ad signal active, OR
  - Future: Google Trends score >= 40, OR
  - Future: YouTube video count >= 20 for keyword

-> Eligible decisions: TEST or WATCH (based on margin threshold)

### MEDIUM confidence

At least one of:
- shipping_cost is estimated (not confirmed) but margin still likely positive
- ebay_benchmark_confidence is LOW but listing count >= 5
- Demand signal is eBay only (no TikTok/Google/YouTube yet)
- matching_confidence is MEDIUM

None of:
- Hard risk flags
- Negative margin
- supplier_cost missing

-> Eligible decisions: WATCH or NEEDS_ENRICHMENT
   May reach TEST if margin is strong_margin and operator accepts estimated shipping.

### LOW confidence

Any of:
- Only supplier data exists (no market benchmark)
- ebay_benchmark_confidence is LOW with listing count < 5
- matching_confidence is LOW
- shipping_cost is None AND product_weight_kg >= 0.3
- No demand signal of any kind

-> Eligible decisions: NEEDS_ENRICHMENT or WATCH (never TEST)

### Confidence caps on decisions

  LOW confidence  -> cannot produce TEST decision
  Any hard risk   -> always REJECT regardless of confidence or margin
  unknown_margin  -> cannot produce TEST decision
  negative_margin -> always REJECT

---

## 13. Scoring components

The following scoring components are proposed for future implementation.
Do not implement yet. Define conceptually to guide schema and Phase B output.

### demand_score (0-100)

Composite of:
- eBay listing count (normalized to 0-40 points)
  - >= 50 listings: 40 pts
  - 20-49: 30 pts
  - 10-19: 20 pts
  - 5-9: 10 pts
  - < 5: 0 pts
- Future TikTok ad signal (0-20 pts): active ads for keyword = 20, none = 0
- Future Google Trends score (0-20 pts): interest >= 60 = 20, 40-59 = 10, < 40 = 0
- Future YouTube content signal (0-20 pts): video_count >= 50 = 20, 20-49 = 10, < 20 = 0

Current (without pending signals): max 40/100

### supply_score (0-100)

- supplier_cost present: 30 pts
- image_url present: 20 pts
- product_weight_kg present: 20 pts
- supplier_availability = True: 20 pts
- cj_pid present: 10 pts

Max: 100

### margin_score (0-100)

- strong_margin: 100
- acceptable_margin: 70
- weak_margin: 40
- unknown_margin: 0
- negative_margin: -50 (triggers REJECT)

### risk_score (0 = no risk, higher = more risk)

- restricted_category_risk: +50
- branded_counterfeit_risk: +50
- medical_claims_risk: +40
- battery_risk: +30
- fragile_risk: +20
- heavy_shipping_risk: +20

Any risk_score >= 40 -> REJECT

### confidence_score (0-100)

- supplier_cost present: 25 pts
- market benchmark present and confidence MEDIUM/HIGH: 25 pts
- shipping_cost present (confirmed): 25 pts
- at least one demand signal: 25 pts

Max: 100

Used to cap final_decision:
- confidence_score < 25: only REJECT or NEEDS_ENRICHMENT
- confidence_score 25-49: WATCH or NEEDS_ENRICHMENT
- confidence_score 50-74: WATCH or TEST (margin dependent)
- confidence_score >= 75: eligible for TEST

### final_decision derivation

  if risk_score >= 40 -> REJECT
  elif negative_margin -> REJECT
  elif confidence_score < 25 -> NEEDS_ENRICHMENT
  elif unknown_margin -> NEEDS_ENRICHMENT
  elif confidence_score >= 50 AND margin_score >= 70 AND demand_score >= 20
       -> TEST (if no caution flags) or WATCH
  elif confidence_score >= 25 -> WATCH
  else -> NEEDS_ENRICHMENT

Hard rules (section 11) always run first and override score-based logic.

---

## 14. Decision reason system

Every decision must output a list of human-readable reason strings.
Operators read these to understand the decision without interpreting scores.

### Positive reason examples (support TEST or WATCH)

  "Supplier cost confirmed: $X.XX per unit"
  "Product is lightweight (Y kg) - standard shipping likely"
  "eBay benchmark supports retail price of $Z (based on N listings)"
  "Product image available - offer can be prepared"
  "eBay demand evidence: N active listings found"
  "Estimated net margin is strong: approx $M per unit"
  "No hard risk flags identified"

### Caution reason examples (support WATCH or NEEDS_ENRICHMENT)

  "Shipping cost not yet confirmed - estimated at flat rate"
  "eBay retail benchmark is weak (fewer than 5 matching listings found)"
  "Product-to-market matching confidence is medium"
  "TikTok ad signal pending - awaiting approval"
  "Google Trends signal pending - alpha access not yet received"
  "YouTube content signal not yet available"
  "Product weight exceeds lightweight threshold - shipping cost uncertain"
  "Estimated CAC is a default assumption ($10), not from real campaigns"
  "Retail price is an estimate from CJ suggested range, not confirmed market data"

### Reject reason examples (support REJECT)

  "Restricted or regulated product category"
  "Suspected branded or counterfeit item - brand name detected in title"
  "Medical or health claims detected in product description"
  "Estimated net margin is negative: retail benchmark minus costs = $-X"
  "No reliable market benchmark found on eBay (fewer than 3 listings)"
  "Supplier cost equal to or above market benchmark"
  "No product image available - offer cannot be prepared"
  "Product previously rejected - duplicate source ID"
  "Heavy product with no confirmed shipping cost and large weight"

### Reason generation rules

- Reasons are generated by the decision engine at evaluation time, not stored as static text.
- Every active risk flag generates a reason string.
- Every missing critical field generates a reason string.
- Every margin calculation step that was completed generates a confirmation reason.
- Every missing demand signal generates a pending/caution reason.
- Reasons should reference specific values where possible (e.g., actual supplier cost,
  actual listing count, actual estimated margin).

---

## 15. Missing data and next action

### next_action value definitions

  run_cj_detail_enrichment
    What: call GET /v1/product/query?pid={cj_pid} for this product
    When: retail price estimate missing; CJ Phase 2 not yet run for this product
    Prerequisite: cj_pid must be present

  run_cj_shipping_enrichment
    What: call GET /v1/product/variant/query + POST /v1/logistic/freightCalculate
    When: shipping_cost is None
    Prerequisite: cj_pid and cj_vid (or ability to fetch vid from detail endpoint)

  run_ebay_benchmark
    What: run eBay keyword search for this product, compute price statistics
    When: ebay_benchmark_confidence is None or ebay_listing_count = 0
    Prerequisite: normalized_title must exist

  run_youtube_signal_if_approved
    What: call YouTube Data API search.list for product keyword
    When: YouTube connector is active (pending owner approval and setup)
    Prerequisite: YOUTUBE_API_KEY set + connector active

  wait_for_tiktok_signal
    What: no immediate action; TikTok access is pending
    When: TikTok is the main missing demand signal and no substitute exists
    Status: blocking on TikTok Developer Support response

  wait_for_google_trends_signal
    What: no immediate action; Google Trends alpha is pending
    When: Google Trends is the main missing search signal
    Status: blocking on Google alpha invitation at admin@zaryotech.com

  operator_review_required
    What: human review is needed before decision can proceed
    When: borderline risk flags, unclear category, or manual verification needed
    Example: product is a health/wellness item with ambiguous claims

  prepare_test_offer
    What: create product page, test ad creative, and small test campaign
    When: decision = TEST
    Prerequisite: image_url present, supplier confirmed, margin confirmed

  reject_product
    What: mark product as rejected in DB; do not add to test queue
    When: decision = REJECT
    Recovery: only re-evaluate if new data changes the rejection condition

  keep_watchlist
    What: add to watchlist, revisit when pending signals become available
    When: decision = WATCH
    Trigger for re-evaluation: TikTok approval, Google Trends approval, YouTube active

### Example decision + next_action combinations

  Scenario: shipping_cost = None, weight = 0.8 kg
    decision:    NEEDS_ENRICHMENT
    next_action: run_cj_shipping_enrichment
    reason:      "Shipping cost not confirmed. Product weight (0.8 kg) exceeds lightweight
                  threshold - cannot estimate reliably."

  Scenario: margin strong, risk low, demand evidence present
    decision:    TEST
    confidence:  HIGH
    next_action: prepare_test_offer
    reason:      "Supplier cost $X, estimated retail $Y, shipping estimated at $Z,
                  estimated net margin $M. eBay benchmark HIGH confidence (N listings).
                  No hard risk flags."

  Scenario: risk flag detected (brand name in title)
    decision:    REJECT
    next_action: reject_product
    reason:      "Branded/counterfeit risk: brand name detected in CJ product title."

  Scenario: eBay benchmark weak, shipping missing
    decision:    NEEDS_ENRICHMENT
    next_action: run_ebay_benchmark
    missing_data: ["ebay_median_price", "shipping_cost"]
    reason:       "Market benchmark is absent - fewer than 3 matching eBay listings found.
                   Shipping cost not confirmed."

  Scenario: supplier cost confirmed, benchmark weak, no hard risk
    decision:    WATCH
    confidence:  LOW
    next_action: keep_watchlist
    reason:      "Supplier cost confirmed but retail benchmark is weak. Demand signals pending.
                  Add to watchlist and re-evaluate after enrichment or new signal sources."

---

## 16. Frontend and export requirements

The operator-facing dashboard and export should surface decision outputs as primary columns.

### Proposed dashboard columns (future implementation)

  decision              TEST | WATCH | NEEDS_ENRICHMENT | REJECT
  confidence            HIGH | MEDIUM | LOW
  margin_status         strong | acceptable | weak | unknown | negative
  estimated_net_margin  Dollar value or "unknown"
  supplier_cost         CJ supplier cost
  benchmark_price       eBay median price (or "not available")
  shipping_cost         Confirmed or estimated value (or "missing")
  estimated_fees        Estimated platform + payment fees
  missing_data          Comma-separated list of absent critical fields
  next_action           Single action code
  risk_flags            Comma-separated list of active risk flags
  decision_reasons      Full list (expandable in UI, comma-separated in export)
  matching_confidence   HIGH | MEDIUM | LOW | NONE
  image_url             Product image (displayed in dashboard)
  source                Source connector name
  category              Product category
  country               Target market

### Operator experience design principles

The operator sees:
  1. WHAT the decision is (TEST / WATCH / NEEDS_ENRICHMENT / REJECT)
  2. WHY it was decided (readable reason list)
  3. WHAT IS MISSING (missing_data list)
  4. WHAT TO DO NEXT (next_action)

The operator should never need to interpret a raw number to understand what to do.
The decision engine replaces score interpretation with explicit action guidance.

### Export format extension

Existing /export/products endpoint should be extended to include:
  decision, confidence, margin_status, estimated_net_margin,
  missing_data (JSON array), next_action, risk_flags (JSON array),
  decision_reasons (JSON array), matching_confidence

This extension should be non-breaking: existing fields remain unchanged,
new fields are additive.

---

## 17. Feedback loop from real tests

When a product is tested via a real ad campaign, results should be recorded and
feed back into the decision engine's threshold calibration over time.

### Test result fields

  tested_at              ISO 8601 datetime when test was started
  test_duration_days     How many days the test ran
  ad_spend               Total ad spend in USD
  impressions            Total ad impressions
  clicks                 Total clicks
  ctr                    Click-through rate (clicks / impressions)
  cpc                    Cost per click (ad_spend / clicks)
  add_to_cart            Number of add-to-cart events
  checkout_started       Number of checkout starts
  purchases              Number of completed purchases
  revenue                Total revenue from test
  roas                   Return on ad spend (revenue / ad_spend)
  cpa                    Cost per acquisition (ad_spend / purchases)
  test_result            win | loss | break_even | inconclusive
  operator_notes         Free text notes from operator post-test

### How feedback improves the engine

Losing products (test_result = loss):
  - Identify patterns in what kinds of products fail: category, weight, margin level, demand signal.
  - Tighten rejection rules for those patterns.
  - E.g., if all products with margin_status = weak_margin lose, lower the TEST eligibility
    threshold to acceptable_margin minimum.

Winning products (test_result = win):
  - Calibrate scoring thresholds: what margin level, demand signal strength, and
    matching confidence reliably predicted success.
  - Expand confidence to similar products.

Inconclusive tests:
  - May indicate: budget too low, creative quality issue, audience targeting issue.
  - These should not automatically change engine thresholds.
  - Record operator_notes for context.

The feedback loop is not implemented in Phase B or C. It is a Phase G concern.
Design the schema to support it from Phase C onward so it does not require migration later.

---

## 18. Implementation phases

### Phase A - Documentation and schema review (current phase)
- Review existing DB fields (products table, normalize_candidate output)
- Identify which decision input fields already exist
- Identify which fields are missing and need to be added
- No code changes
- Output: list of existing fields, list of missing fields, migration plan for Phase C

### Phase B - Dynamic decision output without schema change
- Implement a decision_engine() function in Python
- Takes a product dict (from DB) as input
- Outputs a decision dict: {decision, confidence, reasons, missing_data, risk_flags, next_action}
- Add decision output to /products API response (computed on-the-fly, not persisted)
- Add decision columns to /export/products output
- No DB migration required
- Minimal risk: no data changes, fully reversible
- This is the RECOMMENDED FIRST IMPLEMENTATION STEP

### Phase C - Persist decision fields to DB
- Add columns to products table: decision, confidence, decision_reasons (JSON),
  missing_data (JSON), risk_flags (JSON), next_action
- Run migration on existing products
- Schedule or trigger re-evaluation when enrichment data changes
- After Phase B validates the model, Phase C makes it persistent

### Phase D - eBay/CJ matching
- Implement keyword extraction from normalized_title
- Implement eBay benchmark query with keyword
- Compute price statistics (median, avg, min, max, listing count)
- Assign matching_confidence
- Store as ebay_* fields per product
- Update decision engine to use benchmark fields

### Phase E - CJ enrichment Phase 2 and Phase 3
- Phase 2: implement GET /v1/product/query?pid= enrichment
  - Add suggestSellPrice parsing
  - Add retail_price_suggestion field
- Phase 3: implement variant + shipping endpoint flow
  - Fetch cj_vid from variant endpoint
  - Call freight calculate endpoint
  - Add shipping_cost field
  - Update decision engine: shipping_cost present allows TEST decisions for more products

### Phase F - Frontend and export update
- Add decision columns to dashboard UI (index.js or new dashboard page)
- Show decision badge: color-coded TEST/WATCH/NEEDS_ENRICHMENT/REJECT
- Show reasons in expandable panel
- Show next_action as clickable operator button where applicable
- Extend /export/products CSV/JSON with decision fields

### Phase G - Feedback loop
- Add test result fields to products table
- Build test result entry form (operator enters results after campaign)
- Store results, compute roas, cpa, test_result
- Future: threshold adjustment based on win/loss pattern analysis

---

## 19. Recommended immediate next implementation phase

### Start with Phase B

Phase B is the recommended first implementation step for the following reasons:

  Low risk:
    No DB schema changes. No migration. No data loss possible.
    Decision output is computed at query time from existing fields.
    Fully reversible: remove the decision_engine() call to restore previous behavior.

  Immediate value:
    Operators immediately see TEST/WATCH/REJECT/NEEDS_ENRICHMENT for every product.
    They see why (reasons list). They see what to do next (next_action).
    No waiting for enrichment endpoints or new connectors.

  Model validation:
    Phase B lets the model run against real CJ + eBay data in the DB before
    committing to schema changes. If the logic is wrong, fix it cheaply in code
    before it is frozen into a migration.

  Guides Phase E priority:
    After Phase B runs, the NEEDS_ENRICHMENT output will show which fields are
    most commonly missing. This tells us whether to prioritize:
    - CJ Phase 2 (if retail_price is the most common missing field)
    - CJ Phase 3 (if shipping_cost is the most common missing field)
    - eBay benchmark (if market_price_evidence is absent most often)

  Does not require new connectors:
    Phase B works entirely on data already in the DB from CJ and eBay.
    TikTok, Google Trends, and YouTube are noted as pending signals but
    do not block Phase B output.

### After Phase B

Do not immediately move to Phase C (schema migration).
Let Phase B run against real data for at least one review cycle.
Evaluate:
  - What is the most common NEEDS_ENRICHMENT reason?
  - What fraction of products reach TEST confidence?
  - Are there systematic false positives (products scored TEST that would fail on review)?

Then choose:
  - Phase C + Phase D (persist + eBay matching) if model validates well
  - Phase E first if a specific enrichment field is blocking most decisions
  - YouTube setup (if content signal is the most impactful missing piece)

---

## 20. Risks and edge cases

  False product matching
    Risk: CJ "posture corrector" matched to a premium branded eBay item inflates benchmark.
    Mitigation: brand keyword filter during eBay search, price range filtering,
                confidence downgrade on mismatched prices.

  Weak eBay benchmark
    Risk: only 2-3 eBay listings found; median price is unreliable.
    Mitigation: minimum listing threshold (3+) for LOW confidence, 10+ for MEDIUM,
                20+ for HIGH. Below 3: no benchmark assigned.

  Missing shipping cost
    Risk: net margin appears positive but shipping wipes it out.
    Mitigation: treat NEEDS_ENRICHMENT strictly - do not allow TEST without confirmed
                or reasonably estimated shipping. Phase 3 must run before TEST is possible
                for heavy products.

  Misleading content signals (YouTube, Meta)
    Risk: high video view count for a product does not mean buyers are purchasing it.
    Example: a viral fail video about a cheap product gets millions of views.
    Mitigation: content signals are MEDIUM weight, never sole basis for TEST decision.
                Demand evidence requires eBay or ad signal at minimum.

  Over-scoring incomplete data
    Risk: a product with supplier_cost + image but no benchmark and no shipping
          gets a high score because the score rewards each present field.
    Mitigation: confidence caps (section 12) prevent TEST when critical fields are absent.
                Score alone never produces a decision - hard rules and confidence caps apply.

  Duplicate products
    Risk: same product appears multiple times in DB (re-discovered via different keywords).
    Mitigation: dedup by source_item_id at ingestion. Decision engine checks for
                existing rejected decision before re-evaluating.

  Country mismatch
    Risk: CJ product ships from China; eBay benchmark from UK market.
          Retail prices, shipping costs, and demand are not comparable.
    Mitigation: enforce country field consistency. Default to US market.
                eBay search should always use regionCode=US + currency=USD.

  Currency mismatch
    Risk: supplier cost in USD but eBay prices in GBP or EUR.
    Mitigation: normalize all prices to USD at fetch time. Flag non-USD prices.

  Restricted products
    Risk: product is a supplement, medical device, or regulated item that appears
          benign on title but requires compliance review.
    Mitigation: category-based flag list + keyword detection in title and description.
                Flag for operator_review_required, not auto-REJECT, for borderline cases.

  Unknown fees and CAC
    Risk: assuming 13% fees and $10 CAC when actual values are different.
    Mitigation: mark these as estimated in decision_reasons. Do not let estimated margin
                alone produce HIGH confidence. Require operator confirmation before TEST.

---

## 21. Final recommendation

### Build the Product Decision Engine next.

The MVP has real data from two live sources (CJ Dropshipping and eBay). That data is being
collected and normalized. What is not happening is a structured decision being made about
each product. Without the decision engine, operators are looking at raw scores and making
manual judgments. That does not scale and it does not capture institutional knowledge.

The decision engine is the highest-leverage next build because:
  - It works on data that already exists in the DB (no new connectors needed).
  - It immediately produces operator-visible output (TEST / WATCH / REJECT / NEEDS_ENRICHMENT).
  - It surfaces which enrichment steps are actually blocking decisions (guides Phase E priority).
  - It makes the missing data visible and actionable (missing_data + next_action).
  - It is reversible at Phase B (no schema migration risk).

### Do not implement YouTube yet.

YouTube setup requires an owner decision and GCP work. More importantly, YouTube is a
content demand signal - it raises confidence on already-promising products. It does not
help evaluate products that currently have no market benchmark or no shipping cost.
The decision engine will show exactly what is missing most often. YouTube should wait
until that picture is clear.

### Do not start CJ Phase 2/3 yet.

CJ Phase 2 (retail price) and Phase 3 (shipping cost) are high-value enrichment steps.
But they should be prioritized based on what the decision model shows is the most common
blocker. If Phase B output shows that 80% of NEEDS_ENRICHMENT decisions are blocked by
missing shipping_cost, Phase E (Phase 3 shipping) becomes the obvious next priority.
If 80% are blocked by missing retail benchmark, Phase E Phase 2 (detail endpoint) comes first.
Running Phase B first gives a data-driven answer to this question.

### Implementation order recommendation

  1. PRODUCT_DECISION_ENGINE_PLAN.md (this document) - complete
  2. Phase A: schema review (identify existing vs missing fields)
  3. Phase B: dynamic decision output, no schema changes
  4. Evaluate Phase B output against real data
  5. Choose: Phase D (eBay matching) or Phase E (CJ enrichment) based on most common blockers
  6. Phase C: schema migration when model is stable
  7. YouTube setup: when decision model shows content signal is the key missing piece
  8. Phase F: frontend update
  9. Phase G: feedback loop (after first real tests run)

---

## Checkpoint files referenced

| File | Covers |
|---|---|
| `CHECKPOINT_CJ_DROPSHIPPING.md` | CJ live status, Phase 2/3 roadmap |
| `CHECKPOINT_TIKTOK_PENDING_ACCESS.md` | TikTok pending access |
| `CHECKPOINT_GOOGLE_TRENDS_PENDING_ACCESS.md` | Google Trends alpha application |
| `CHECKPOINT_META_AD_LIBRARY_AUDIT.md` | Meta audit - postponed |
| `CHECKPOINT_YOUTUBE_DATA_API_AUDIT.md` | YouTube audit - proceed_to_setup pending owner approval |
| `SOURCE_STRATEGY_MAP.md` | Full source map with stage definitions and decision gates |
| `MASTER_PROJECT_STATUS.md` | Cross-connector summary |
| `PRODUCT_DECISION_ENGINE_PLAN.md` | This file - decision engine design |
