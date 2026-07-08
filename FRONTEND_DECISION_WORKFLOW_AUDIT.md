# Frontend Decision Workflow Audit

Last updated: 2026-07-08
Covers: frontend/pages/index.js only (single-file Next.js frontend)
Purpose: identify where Phase B decision output is and is not surfaced to the operator

---

## 1. Scope

Phase B (commit 8006d40) added 8 decision fields to the `/products` API response and to
`/export/products`. This audit confirms whether those fields are visible in the operator UI
and recommends the minimum implementation to surface them.

No code was changed during this audit. No backend changes. No DB changes. No external APIs.

---

## 2. Frontend File Inventory

| File | Role |
|---|---|
| `frontend/pages/index.js` | Only frontend file. Single-page React app, 900 lines. |

No components directory. No separate CSS file. All styles are inline `<style jsx global>`.

---

## 3. API Integration Points

| Location | Endpoint | When |
|---|---|---|
| `load()` function, line 117 | `GET /products` | On mount + after every mutating action |
| `load()` function, line 118 | `GET /reports/daily` | On mount + after every mutating action |
| `openDetail()` function, line 131 | `GET /products/{id}` | On product row click |
| `runDiscovery()` function, line 151 | `POST /discovery/multisource` | On discovery form submit |
| `downloadExport()` function, line 103 | `GET /export/products?filter=...&format=...` | On export button click |
| `saveReviewStatus()` function, line 76 | `PATCH /products/{id}/review` | On pipeline status change |
| `toggleShortlist()` function, line 96 | `POST /products/{id}/shortlist` | On star button click |

The `GET /products` response (via `load()`) populates the `products` state array which drives
every product table, pipeline, shortlist, and filter in the UI. All 8 decision fields are
present in every item in that array since Phase B. They are simply not rendered.

---

## 4. Decision Fields: Available vs Displayed

Phase B added these 8 fields to every item returned by `GET /products`:

| Field | Type | Example value | Displayed? |
|---|---|---|---|
| `decision` | string | "NEEDS_ENRICHMENT" / "REJECT" / "TEST" / "WATCH" | **NO** |
| `decision_confidence` | string | "HIGH" / "MEDIUM" / "LOW" | **NO** |
| `margin_status` | string | "STRONG" / "ACCEPTABLE" / "WEAK" / "NEGATIVE" / "UNKNOWN" | **NO** |
| `estimated_net_margin` | float or null | 0.32 | **NO** |
| `missing_data` | list of strings | ["image_url", "shipping_cost"] | **NO** |
| `risk_flags` | list of strings | ["fragile"] | **NO** |
| `decision_reasons` | list of strings | ["Missing: image_url"] | **NO** |
| `next_action` | string | "operator_review" / "run_cj_shipping_enrichment" / etc. | **NO** |

**All 8 Phase B decision fields are invisible to the operator. Zero are rendered.**

---

## 5. What the UI Currently Shows (Per Section)

### 5a. Discovered Products table (lines 554-619)

Columns rendered:
- Shortlist star button
- Product: source pill + name
- Country
- Price (retail_price)
- Score (score/60)
- Recommendation (old scoring `recommendation` field via `<Pill>` component)
- Link (source_url anchor)
- Discovered date

Missing from Phase B: decision, decision_confidence, margin_status, next_action,
missing_data count, risk_flags. The `recommendation` column shows the old scoring verdict
("Strong candidate", "Reject", "Watchlist", "Test with small budget") - NOT the new
`decision` field ("TEST", "REJECT", "NEEDS_ENRICHMENT", "WATCH").

### 5b. Discovered Products filters (lines 488-552)

Current filters:
- Sort: newest / highest score / lowest price / highest price
- Recommendation filter: driven by `p.recommendation` (old scoring field)
- Country filter
- "Has source link" checkbox (filters by source_url presence)
- "Shortlisted only" checkbox

Missing: no filter by `decision`, no filter by `next_action`, no filter for missing
image_url, no filter for missing supplier_cost, no filter for missing shipping_cost.

### 5c. Product Review Pipeline / kanban (lines 418-479)

Groups products by `review_status` (new / researching / test_candidate / winner / rejected).
Each card shows: source pill, price, old `recommendation` Pill.
Missing: no `decision` badge, no `next_action`, no `missing_data` indicator.

### 5d. Shortlisted Products cards (lines 334-416)

Shows: source pill, name, price, score, old `recommendation` Pill, review_status select,
operator_notes input, shortlisted_at date.
Missing: no decision fields.

### 5e. Sample/Manual Products table (lines 641-670)

Shows: name, category, country, score, old `recommendation` Pill, net_profit_per_order
(raw scoring field), scoring `confidence` level.
Missing: no Phase B decision fields.

### 5f. Discovery result cards (lines 300-329)

Shows: name, price, source pill, link, score/60.
Note: discovery result cards display candidates returned by `/discovery/multisource`
(not from the products DB). Decision fields are NOT in that response shape - this
is a separate concern from the main product list.

### 5g. Detail drawer (lines 857-899)

Opened by clicking any product row. Reads from `GET /products/{id}`.
Note: `GET /products/{id}` was NOT updated in Phase B - it returns the old scoring
shape (`scoring.recommendation`, `scoring.categories`, `scoring.filter_reasons`,
`scoring.recommendation_reason`, `scoring.net_profit_per_order`, `scoring.confidence`).
The 8 decision fields are NOT available in the detail drawer's data source.

Decision fields available only through `GET /products` (list endpoint), not through
`GET /products/{id}` (detail endpoint). This is a known Phase B scope decision.

### 5h. Operator Reports / export (lines 622-638)

Buttons trigger `GET /export/products?filter=...&format=json|csv`.
The export DOES include all 8 decision fields in the file download (added in Phase B
`EXPORT_FIELDS`). However, the operator has no UI visibility into which products fall
into which decision categories before downloading.

---

## 6. Pill Component Gap

```js
const VERDICT_COLOR = {
  "Reject": "#e5484d",
  "Watchlist": "#f5a623",
  "Test with small budget": "#4a90d9",
  "Strong candidate": "#46a758",
};

function Pill({ verdict }) {
  return <span className="pill" style={{ background: VERDICT_COLOR[verdict] || "#666" }}>
    {verdict}
  </span>;
}
```

`Pill` is wired to the old scoring `recommendation` strings. The new Phase B `decision`
values ("NEEDS_ENRICHMENT", "REJECT", "TEST", "WATCH") would render with background `#666`
(fallback gray) if passed to the existing `Pill`. A separate `DecisionBadge` component
with its own color map is needed.

Appropriate colors for Phase B decision values:
- REJECT - red (#e5484d)
- NEEDS_ENRICHMENT - amber (#f5a623)
- TEST - blue (#4a90d9)
- WATCH - gray-blue (#6b7fa3)

---

## 7. Filter Gap: discoveryFilterRec

```js
const discoveryRecs = [...new Set(discoveredProducts.map((p) => p.recommendation).filter(Boolean))].sort();
```

The recommendation filter is built from `p.recommendation` (old scoring field). It would
need to be duplicated or replaced with a `decision` filter using `p.decision`.

The two fields carry related but distinct information:
- `p.recommendation`: scoring output ("Strong candidate", "Watchlist", etc.)
- `p.decision`: Phase B decision engine output ("TEST", "NEEDS_ENRICHMENT", etc.)

Both exist in the API response. The decision filter is more actionable for operator triage
because it directly maps to what the operator must do next (enrich / reject / test / watch).

---

## 8. next_action Values in Current Data

From Phase B runtime smoke test (76 products, 2026-07-08):
- NEEDS_ENRICHMENT = 48 products
- REJECT = 28 products
- WATCH = 0
- TEST = 0

Known next_action values produced by decision_engine.py:
- `"run_cj_shipping_enrichment"` - CJ products with item_id but missing shipping_cost
- `"operator_review"` - products missing enrichable data (image_url, retail_price, supplier_cost, shipping_cost without a direct API path)
- `"reject"` - eliminated or negative margin
- `"add_to_watch"` - WATCH decision
- `"run_small_budget_test"` - TEST decision

The `"operator_review"` next_action will be the most common by far given current data.
Grouping products by next_action (or filtering by it) directly answers "what do I do now?"

---

## 9. missing_data Field Analysis

`missing_data` is a list of field name strings returned per product. From current data:
- `image_url` missing in 71/76 products
- `shipping_cost` missing in 42/76 products
- `supplier_cost` missing in 40/76 products
- `retail_price` missing in ~5 CJ products

The operator has no way to see this breakdown without downloading and parsing the CSV/JSON
export. A "missing_data count" column (e.g., "3 fields missing") and a filter for specific
missing fields would immediately surface which products need what.

---

## 10. Recommended Display: Discovered Products Table

Proposed additional columns (in priority order):

| Column | Source field | Display format | Priority |
|---|---|---|---|
| Decision | `p.decision` | Colored badge (NEEDS_ENRICHMENT / REJECT / TEST / WATCH) | HIGH |
| Next action | `p.next_action` | Short label / pill | HIGH |
| Missing | `p.missing_data` | Count badge e.g. "3 fields" / tooltip with list | HIGH |
| Margin | `p.margin_status` | Short label (STRONG / ACCEPTABLE / WEAK / NEGATIVE / UNKNOWN) | MEDIUM |
| Confidence | `p.decision_confidence` | HIGH / MEDIUM / LOW text | MEDIUM |
| Reasons | `p.decision_reasons` | Truncated first reason + tooltip | LOW |

The discovery table currently has 8 columns. Adding all 6 would be visually crowded.
Minimum useful set: Decision + Next action + Missing count (3 columns).

---

## 11. Recommended Filters

| Filter | Source field | Type | Priority |
|---|---|---|---|
| Decision | `p.decision` | Select: All / NEEDS_ENRICHMENT / REJECT / TEST / WATCH | HIGH |
| Next action | `p.next_action` | Select: All / operator_review / run_cj_shipping_enrichment / ... | HIGH |
| Source | `p.source` | Select: All / ebay / cj_dropshipping | MEDIUM |
| Missing image_url | `p.missing_data.includes("image_url")` | Checkbox | MEDIUM |
| Missing supplier_cost | `p.missing_data.includes("supplier_cost")` | Checkbox | MEDIUM |
| Missing shipping_cost | `p.missing_data.includes("shipping_cost")` | Checkbox | LOW |

The `decision` filter replaces or supplements the existing `recommendation` filter which
uses the old scoring field. Both can coexist during transition.

---

## 12. Implementation Options

### Option A - Display decision columns only

**Scope:** Add 3 columns to the Discovered Products table: Decision badge, next_action
label, missing_data count. No new filter logic. No new API calls.

**Changes required (frontend only):**
- Add `DECISION_COLOR` map constant
- Add `DecisionBadge` component (similar to `Pill`, different color map and labels)
- Add 3 `<th>` headers to Discovered Products table
- Add 3 `<td>` cells per row: `DecisionBadge`, `p.next_action` text, `p.missing_data?.length` count
- No backend change, no DB change, no API change

**Estimated lines of new code:** ~30-40 lines
**Risk:** Very low. Data already in API response. No logic change.
**Operator gain:** Immediately see which 48 products need enrichment and why, which 28
are rejected, and what the next action is for each. Phase B output becomes visible.

### Option B - Add decision-based filters

**Scope:** Option A plus decision filter, next_action filter, source filter, missing-field
checkboxes in the Discovered Products controls bar.

**Changes required (frontend only):**
- Everything in Option A
- Add 2 new state variables: `filterDecision`, `filterNextAction`
- Add 2 `<select>` dropdowns to disc-controls bar
- Extend `visibleDiscovered` filter chain with 2 new `.filter()` calls
- Optional: add 3 missing-field checkboxes (image_url / supplier_cost / shipping_cost)

**Estimated lines of new code:** ~60-80 lines (including Option A)
**Risk:** Low. All data client-side. Filter logic is identical pattern to existing filters.
**Operator gain:** Can isolate "all CJ shipping enrichment candidates", "all operator review
items", "all rejected", "all missing image_url" in one click. Triage becomes fast.

### Option C - Operator action queue grouped by next_action

**Scope:** New section or replacement for the current pipeline kanban. Groups products by
`next_action` rather than `review_status`. Columns: run_cj_shipping_enrichment /
operator_review / run_small_budget_test / add_to_watch / reject.

**Changes required (frontend only):**
- Everything in Option B
- New `ActionQueue` section component with kanban-style columns grouped by `next_action`
- OR: modify existing Pipeline section to add a second grouping mode toggle

**Estimated lines of new code:** ~120-160 lines (including A+B)
**Risk:** Medium. Larger surface area. Existing Pipeline section must stay functional.
**Operator gain:** Action-oriented view replaces status-oriented view. Operator sees
"here are the 5 CJ products to run enrichment on" as a distinct column, not mixed in
with everything else. Highest workflow value but more work.

---

## 13. Recommendation

**Start with Option A.**

Rationale:
- Zero backend risk. Zero DB risk. Zero API risk. Pure display change.
- Surfaces Phase B output which is already computed and present in every API response.
- The operator currently cannot see `decision`, `next_action`, or `missing_data` at all.
  Three new columns fix that completely with ~35 lines of code.
- Option B (filters) adds moderate value but the operator can already sort/scroll through
  76 products; filters are most valuable when the list grows beyond ~150.
- Option C (action queue) is highest value long-term but should follow A and B, not precede them.

**Recommended implementation order:**
1. Option A - decision columns (approve and implement first)
2. Option B - decision filters (can be combined with A or follow immediately)
3. Option C - action queue (schedule when product count makes triage unwieldy)

**No implementation starts without explicit owner approval.**

---

## 14. Detail Drawer Gap (Separate Issue)

`GET /products/{id}` (used by the detail drawer) was not updated in Phase B. It returns
the old scoring shape only. Decision fields are not available in the drawer.

Fixing this requires updating the `/products/{pid}` endpoint in `backend/main.py` to
include `_summary_with_decision()` output (same wrapper already used on the list endpoint).
This is a 1-2 line backend change. It is a separate decision from the frontend columns.

Not recommended to block Option A on this. The table columns are sufficient for triage.
Updating the detail drawer is a follow-on step after Option A is live.

---

## 15. Export Note

`GET /export/products` already includes all 8 decision fields in both JSON and CSV output
(added in Phase B `EXPORT_FIELDS`). The operator can download a CSV now and see decision
output. The UI gap is that the operator cannot see or filter by these fields before
deciding what to export or act on.

---

## 16. Safety Confirmations

- No code modified during this audit
- No backend changes
- No DB changes
- No DB schema changes
- No external APIs called
- No discovery run
- No eBay backfill performed
- No old eBay rows modified
- backend/.env not modified and not printed
- No secrets accessed or exposed

---

## 17. Files Changed

| File | Change |
|---|---|
| `FRONTEND_DECISION_WORKFLOW_AUDIT.md` | Created (this file) |
| `MASTER_PROJECT_STATUS.md` | Updated: eBay backfill postponed, decision UI options added |
| `frontend/pages/index.js` | NOT modified |
| `backend/main.py` | NOT modified |
| `backend/decision_engine.py` | NOT modified |
