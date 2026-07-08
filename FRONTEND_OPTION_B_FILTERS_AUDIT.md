# Frontend Option B Filters Audit

Last updated: 2026-07-08
File inspected: frontend/pages/index.js (post-Option-A state, commit fee074d)
Purpose: plan decision-based filter additions before implementation

No code was changed during this audit.

---

## 1. Current Filter State Variables

Located at lines 106-110 inside `export default function Home()`:

```js
const [discoverySort,             setDiscoverySort]             = useState("newest");
const [discoveryFilterRec,        setDiscoveryFilterRec]        = useState("");
const [discoveryFilterLink,       setDiscoveryFilterLink]       = useState(false);
const [discoveryFilterCountry,    setDiscoveryFilterCountry]    = useState("");
const [discoveryFilterShortlisted,setDiscoveryFilterShortlisted]= useState(false);
```

5 existing state variables. All scoped to the Discovered Products panel. The sort state
is not a filter but sits in the same block for grouping.

---

## 2. Current visibleDiscovered Filter Chain

Located at lines 241-252:

```js
const visibleDiscovered = discoveredProducts
  .filter((p) => !discoveryFilterRec        || p.recommendation === discoveryFilterRec)
  .filter((p) => !discoveryFilterLink       || !!p.source_url)
  .filter((p) => !discoveryFilterCountry    || p.country === discoveryFilterCountry)
  .filter((p) => !discoveryFilterShortlisted || !!p.shortlisted)
  .sort((a, b) => {
    if (discoverySort === "newest")     return (b.discovered_at || "").localeCompare(a.discovered_at || "");
    if (discoverySort === "score")      return (b.score ?? -1) - (a.score ?? -1);
    if (discoverySort === "price_asc")  return (a.retail_price ?? Infinity) - (b.retail_price ?? Infinity);
    if (discoverySort === "price_desc") return (b.retail_price ?? -1) - (a.retail_price ?? -1);
    return 0;
  });
```

Pattern: each filter is a short-circuit — falsy state value = filter inactive, all rows pass.
New filters must follow the same pattern for consistency.

---

## 3. Current discoveryFiltersActive Expression

Line 253:

```js
const discoveryFiltersActive = !!(
  discoveryFilterRec || discoveryFilterLink || discoveryFilterCountry || discoveryFilterShortlisted
);
```

Controls visibility of the "Clear filters" button. Must be extended to include all 5
new filter states so "Clear filters" appears when any new filter is active.

---

## 4. Current Filter UI Section

Located at lines 527-589 inside the `{discoveredProducts.length > 0 && (` section guard.
The section gate at line 519 means filters only render when discovered products exist.

Controls bar structure (lines 527-589):

```
<div className="disc-controls">
  [Sort select]                         — always shown
  [Recommendation select]               — shown only if discoveryRecs.length > 0
  [Country select]                      — shown only if discoveryCountries.length > 1
  [Has source link checkbox]            — always shown
  [★ Shortlisted only checkbox]         — always shown
  [Clear filters button]                — shown only if discoveryFiltersActive
</div>
```

CSS class `disc-controls` uses `display: flex; flex-wrap: wrap; align-items: center; gap: 12px`.
New filter elements will wrap naturally with no CSS change needed.

---

## 5. Current Clear Filters Handler

Lines 579-584:

```js
onClick={() => {
  setDiscoveryFilterRec("");
  setDiscoveryFilterLink(false);
  setDiscoveryFilterCountry("");
  setDiscoveryFilterShortlisted(false);
}}
```

Must be extended with 5 new reset calls. Missing a reset for any new state variable would
leave a ghost-active filter that can't be cleared from the UI.

---

## 6. Derived Data Used by Existing Filters

Lines 239-240:

```js
const discoveryRecs    = [...new Set(discoveredProducts.map((p) => p.recommendation).filter(Boolean))].sort();
const discoveryCountries = [...new Set(discoveredProducts.map((p) => p.country).filter(Boolean))].sort();
```

`discoveryRecs` drives the Recommendation dropdown options dynamically from actual data.
`discoveryCountries` drives the Country dropdown — only shown when more than 1 country exists.

The new Decision and Next Action dropdowns do NOT need dynamic derivation. The set of
valid values is fully determined by the decision engine at commit time:
- `decision`: TEST / WATCH / NEEDS_ENRICHMENT / REJECT (4 known values)
- `next_action`: 7 known values from NEXT_ACTION_LABELS already in the file

Static option lists are safer — no dependency on whether the current DB happens to contain
every value, no empty dropdowns when product count is low.

---

## 7. Recommended New State Variables

Add after line 110 (after the existing `discoveryFilterShortlisted` line), before `reviewDrafts`:

```js
const [discoveryFilterDecision,            setDiscoveryFilterDecision]            = useState("");
const [discoveryFilterNextAction,          setDiscoveryFilterNextAction]          = useState("");
const [discoveryFilterMissingImageUrl,     setDiscoveryFilterMissingImageUrl]     = useState(false);
const [discoveryFilterMissingSupplierCost, setDiscoveryFilterMissingSupplierCost] = useState(false);
const [discoveryFilterMissingShippingCost, setDiscoveryFilterMissingShippingCost] = useState(false);
```

5 new state variables. Same naming convention as existing filters (`discoveryFilter*`).

---

## 8. Recommended Filter Chain Additions

Add 5 new `.filter()` calls after line 245 (after `discoveryFilterShortlisted` filter,
before `.sort(...)`):

```js
.filter((p) => !discoveryFilterDecision
    || p.decision === discoveryFilterDecision)
.filter((p) => !discoveryFilterNextAction
    || p.next_action === discoveryFilterNextAction)
.filter((p) => !discoveryFilterMissingImageUrl
    || (Array.isArray(p.missing_data) && p.missing_data.includes("image_url")))
.filter((p) => !discoveryFilterMissingSupplierCost
    || (Array.isArray(p.missing_data) && p.missing_data.includes("supplier_cost")))
.filter((p) => !discoveryFilterMissingShippingCost
    || (Array.isArray(p.missing_data) && p.missing_data.includes("shipping_cost")))
```

The `Array.isArray()` guard is required — `missing_data` comes from the API as a list
but could be `null` or `undefined` for products where the decision engine returned no
missing fields (e.g., REJECT with all prices present).

---

## 9. Recommended discoveryFiltersActive Update

Replace line 253 with:

```js
const discoveryFiltersActive = !!(
  discoveryFilterRec
  || discoveryFilterLink
  || discoveryFilterCountry
  || discoveryFilterShortlisted
  || discoveryFilterDecision
  || discoveryFilterNextAction
  || discoveryFilterMissingImageUrl
  || discoveryFilterMissingSupplierCost
  || discoveryFilterMissingShippingCost
);
```

All 9 filter states included. The "Clear filters" button appears when any one is active.

---

## 10. Recommended UI Elements

Insert after the "★ Shortlisted only" checkbox block (after line 574), before the
`{discoveryFiltersActive && (` block (line 576):

```jsx
<label className="ctrl-label">
  Decision
  <select value={discoveryFilterDecision} onChange={(e) => setDiscoveryFilterDecision(e.target.value)}>
    <option value="">All</option>
    <option value="NEEDS_ENRICHMENT">NEEDS_ENRICHMENT</option>
    <option value="REJECT">REJECT</option>
    <option value="TEST">TEST</option>
    <option value="WATCH">WATCH</option>
  </select>
</label>

<label className="ctrl-label">
  Next Action
  <select value={discoveryFilterNextAction} onChange={(e) => setDiscoveryFilterNextAction(e.target.value)}>
    <option value="">All</option>
    <option value="operator_review_required">Operator review required</option>
    <option value="run_ebay_benchmark">Run eBay benchmark</option>
    <option value="run_cj_shipping_enrichment">Run CJ shipping enrichment</option>
    <option value="run_cj_detail_enrichment">Run CJ detail enrichment</option>
    <option value="prepare_test_offer">Prepare test offer</option>
    <option value="keep_watchlist">Keep watchlist</option>
    <option value="reject_product">Reject product</option>
  </select>
</label>

<label className="ctrl-check">
  <input type="checkbox" checked={discoveryFilterMissingImageUrl}
    onChange={(e) => setDiscoveryFilterMissingImageUrl(e.target.checked)} />
  Missing image_url
</label>

<label className="ctrl-check">
  <input type="checkbox" checked={discoveryFilterMissingSupplierCost}
    onChange={(e) => setDiscoveryFilterMissingSupplierCost(e.target.checked)} />
  Missing supplier_cost
</label>

<label className="ctrl-check">
  <input type="checkbox" checked={discoveryFilterMissingShippingCost}
    onChange={(e) => setDiscoveryFilterMissingShippingCost(e.target.checked)} />
  Missing shipping_cost
</label>
```

Uses existing CSS classes `ctrl-label` and `ctrl-check` — no new styles needed.

---

## 11. Recommended Clear Filters Handler Update

Replace the existing 4-line reset block (lines 580-583) with 9 resets:

```js
onClick={() => {
  setDiscoveryFilterRec("");
  setDiscoveryFilterLink(false);
  setDiscoveryFilterCountry("");
  setDiscoveryFilterShortlisted(false);
  setDiscoveryFilterDecision("");
  setDiscoveryFilterNextAction("");
  setDiscoveryFilterMissingImageUrl(false);
  setDiscoveryFilterMissingSupplierCost(false);
  setDiscoveryFilterMissingShippingCost(false);
}}
```

---

## 12. Risks and Edge Cases

| Risk | Detail | Mitigation |
|---|---|---|
| `missing_data` is null/undefined | API returns null for products with no missing fields | `Array.isArray(p.missing_data) &&` guard in every missing_data filter |
| `decision` is null/undefined | Products missing decision output would not match any filter value | Short-circuit `!discoveryFilterDecision` handles this correctly - they pass when filter is "All" |
| `next_action` is null/undefined | Same as decision | Same short-circuit pattern handles it |
| Stale `next_action` value in dropdown | A value in the dropdown that no product has is harmless — results in 0 rows, not a crash | Acceptable; operator learns by trying |
| Controls bar overflow on small screens | 9 filter controls is more than the current 5 | `flex-wrap: wrap` is already set; wraps cleanly on narrow viewports |
| "Clear filters" ghost state | Forgetting to add a new state to discoveryFiltersActive | All 5 new states are included in the recommended expression |
| "Clear filters" incomplete reset | Forgetting to add a new state to the reset handler | All 5 new states are in the recommended reset block |
| Combining all 3 missing-field filters | A product must match ALL active filters (AND logic) | Correct — operator would see products missing all 3, which is fine |

---

## 13. Smallest Safe Implementation Scope

Exact changes to `frontend/pages/index.js` only:

| Location | Change | Lines added |
|---|---|---|
| Line 110 (after existing filter state block) | 5 new `useState` declarations | +5 |
| Line 245 (after shortlist filter, before .sort) | 5 new `.filter()` calls | +10 |
| Line 253 (discoveryFiltersActive) | Replace 1-line expression with 9-condition version | +8 |
| Line 574 (after Shortlisted checkbox, before Clear button) | 5 new UI elements (2 selects + 3 checkboxes) | +27 |
| Lines 580-583 (clear handler) | Add 5 new reset calls | +5 |

**Total: ~55 lines added, 1 line replaced. No lines deleted.**
No new components needed. No new helper functions needed. No CSS changes needed.
No backend changes. No DB changes. No API changes.

---

## 14. Files That Would Change If Approved

| File | Change |
|---|---|
| `frontend/pages/index.js` | Only file modified |
| Any backend file | NOT modified |
| Any DB file | NOT modified |

---

## 15. Build Verification Plan

After implementation:
1. `cd frontend && npm run build` — must pass with no errors or warnings
2. `git diff --stat -- frontend/pages/index.js` — must show only 1 file changed
3. Secret scan — no tokens or secrets introduced
4. Mojibake check — no C3 A2 byte pattern

---

## 16. Safety Confirmations

- No code modified during this audit
- No backend changes
- No DB changes
- No external APIs called
- No discovery run
- n8n workflow not modified
- backend/.env not modified and not printed
- No secrets accessed or exposed
- eBay existing-row backfill remains postponed
