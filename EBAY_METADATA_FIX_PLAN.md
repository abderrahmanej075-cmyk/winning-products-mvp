# eBay Metadata Fix Plan

Created: 2026-07-08
Status: plan_only / pending_owner_approval / not_implemented

Depends on: EBAY_IMAGE_PIPELINE_AUDIT.md (root cause confirmed)
Prerequisite for: eBay item_id DB backfill, future eBay re-discovery with enriched metadata

---

## 1. Executive Summary

This plan covers the minimal code change to fix eBay metadata mapping for future
discoveries. Scope is limited to two missing field extractions in one function.

Target fields:
- `item["itemId"]` -> `item_id` on each discovered eBay product
- `item["image"]["imageUrl"]` -> `image_url` on each discovered eBay product

No DB schema change is required. Both columns (`item_id TEXT`, `image_url TEXT`) already
exist in the `products` table and are already handled by `upsert_discovered_candidate()`
in `db.py`.

No external API call is required for the code change or for running tests. Tests use
inline sample dicts that match the eBay Browse API response shape.

Existing DB rows (37 eBay records) are NOT updated by this fix. They require a separate,
explicitly approved backfill phase documented below. This fix applies only to eBay
products discovered after the fix is deployed.

eBay connector freeze rule: no implementation until owner explicitly approves.

---

## 2. Files to Change

| File | Change type | Scope |
|---|---|---|
| `backend/sources/ebay.py` | Modify | Add 2 field extractions to `_ebay_item_to_raw()` (line 165-185) and 2 pass-through keys to `_normalize_candidate()` (line 103-131) |
| `backend/test_ebay_metadata_mapping.py` | Create | New stdlib unittest file; no API calls, no network, no .env |

No changes to:
- `backend/db.py` — persistence already handles `item_id` and `image_url` correctly
- `backend/sources/normalize.py` — already reads `item_id` and `image_url` from candidate dict
- `backend/decision_engine.py` — no change
- `backend/scoring.py` — no change
- `backend/main.py` — no change
- Any CJ, TikTok, Google, YouTube, Meta connector
- Frontend

---

## 3. Exact Mapping Target

### eBay Browse API `item_summary` shape (relevant fields)

```json
{
  "itemId": "v1|158043884007|0",
  "title": "Adjustable Posture Corrector Back Brace",
  "itemWebUrl": "https://www.ebay.com/itm/158043884007?...",
  "price": {"value": "24.99", "currency": "USD"},
  "image": {
    "imageUrl": "https://i.ebayimg.com/images/g/1BsAAeSwJY1qRNGr/s-l225.jpg"
  },
  "shippingOptions": [
    {"shippingCost": {"value": "0.00", "currency": "USD"}}
  ],
  "categories": [{"categoryName": "Health & Beauty"}]
}
```

### Mapping table

| eBay field | Extracted as | Passed through as | Persisted as |
|---|---|---|---|
| `itemId` | `raw["item_id"]` | `candidate["item_id"]` | `products.item_id` |
| `image.imageUrl` | `raw["image_url"]` | `candidate["image_url"]` | `products.image_url` |
| `itemWebUrl` | `raw["item_url"]` | `candidate["source_url"]` | `products.source_url` |
| `price.value` | `raw["price"]` | `candidate["retail_price"]` | `products.retail_price` |
| `supplier_cost` | `raw["supplier_cost"] = None` | `candidate["supplier_cost"] = None` | `products.supplier_cost = NULL` |
| `shippingOptions[0].shippingCost.value` | `raw["shipping_cost"]` | `candidate["shipping_cost"]` | `products.shipping_cost` |

### Fields that must NOT change

- `source_url` mapping (`item_url` -> `source_url`) — unchanged
- `retail_price` mapping (`price.value`) — unchanged
- `supplier_cost = None` — unchanged (no supplier cost from eBay search)
- `shipping_cost` extraction — unchanged (current behavior, may be None if not in response)
- All signal fields (`trends_interest`, `amazon_bsr`, etc.) — all remain None
- `_normalize_candidate()` output keys for all existing fields — unchanged

---

## 4. Implementation Approach

### Option A (recommended) — Fix at `_ebay_item_to_raw()` + `_normalize_candidate()`

Add `item_id` and `image_url` to the raw dict in `_ebay_item_to_raw()` (the function that
reads directly from the eBay API response), then add pass-through keys to
`_normalize_candidate()` (the function that produces the scoring-field-named candidate).

**Changes to `_ebay_item_to_raw()` (backend/sources/ebay.py line 165):**

Current return dict (lines 165-185):
```python
return {
    "title": item.get("title", "").strip(),
    "category": category,
    "country": country,
    "item_url": item.get("itemWebUrl"),
    "price": price,
    "supplier_cost": None,
    "shipping_cost": shipping,
    "weight_kg": None,
    ...
}
```

After fix — add two lines:
```python
return {
    "title": item.get("title", "").strip(),
    "category": category,
    "country": country,
    "item_url": item.get("itemWebUrl"),
    "item_id": item.get("itemId"),                                    # <-- ADD
    "image_url": (item.get("image") or {}).get("imageUrl"),           # <-- ADD
    "price": price,
    "supplier_cost": None,
    "shipping_cost": shipping,
    "weight_kg": None,
    ...
}
```

Note on `image_url` extraction: `(item.get("image") or {}).get("imageUrl")` is safe
when `image` is absent, `None`, or not a dict. A plain `item["image"]["imageUrl"]` would
raise `KeyError` or `TypeError` when the field is absent.

**Changes to `_normalize_candidate()` (backend/sources/ebay.py line 103):**

Current return dict (lines 103-131): does not include `item_id` or `image_url`.

After fix — add two lines after `source_url`:
```python
return {
    "name": raw.get("title", "").strip(),
    "category": raw.get("category", "other"),
    "country": raw.get("country", "US"),
    "source_url": raw.get("source_url") or raw.get("item_url") or raw.get("url") or raw.get("link"),
    "item_id": raw.get("item_id"),      # <-- ADD
    "image_url": raw.get("image_url"),  # <-- ADD
    "retail_price": raw.get("price"),
    ...
}
```

**Total diff: 4 lines added, 0 lines removed.**

**Pros:**
- Fix is at the correct layer — directly where the data is available
- Minimal blast radius: only `_ebay_item_to_raw()` and `_normalize_candidate()` touched
- All downstream functions (`normalize_candidate()` in normalize.py, `upsert_discovered_candidate()`
  in db.py) already handle these fields correctly — no cascade changes needed
- Easy to test: unit test can mock an eBay item dict and call `_ebay_item_to_raw()` directly
- Easy to verify: 4-line diff with no behavioral change to any other field

**Cons:**
- Still requires owner approval since eBay connector is frozen
- Does not fix existing 37 DB rows (separate backfill phase required)

---

### Option B — Add fields after `normalize_candidate()` in `_live_discover()`

Modify `_live_discover()` (line 321) to attach `item_id` and `image_url` to each candidate
after calling `_normalize_candidate()`, by keeping a reference to the original `item` dict.

```python
for item in items:
    raw = _ebay_item_to_raw(item, country)
    candidate = _normalize_candidate(raw)
    candidate["item_id"] = item.get("itemId")                         # <-- ADD
    candidate["image_url"] = (item.get("image") or {}).get("imageUrl") # <-- ADD
    candidates.append(candidate)
```

**Pros:**
- Does not touch `_ebay_item_to_raw()` or `_normalize_candidate()` signatures

**Cons:**
- Higher complexity: field mapping split across two layers (some in `_ebay_item_to_raw`,
  some patched in `_live_discover`)
- Harder to test in isolation (must invoke the collector loop, not just the raw mapper)
- Does not work for the stub path (`_stub_response` also calls `_normalize_candidate` and
  would still produce `item_id=None` and `image_url=None` for stub items)
- Violates the single-responsibility separation already established: `_ebay_item_to_raw()`
  is the eBay-to-raw mapper; patching in the caller breaks that contract

**Recommendation: Option A.** The fix belongs in the two functions whose job is field
mapping. Option B produces a more fragile, harder-to-test design for no benefit.

---

## 5. Tests Required

New file: `backend/test_ebay_metadata_mapping.py`
Runtime: `python -m unittest test_ebay_metadata_mapping` from `backend/` directory
Dependencies: stdlib `unittest` only. No API calls. No network. No `.env`. No httpx.

### Sample eBay item dict for tests

```python
_SAMPLE_ITEM = {
    "itemId": "v1|158043884007|0",
    "title": "Adjustable Posture Corrector",
    "itemWebUrl": "https://www.ebay.com/itm/158043884007?hash=abc",
    "price": {"value": "24.99", "currency": "USD"},
    "image": {
        "imageUrl": "https://i.ebayimg.com/images/g/abc/s-l225.jpg"
    },
    "shippingOptions": [
        {"shippingCost": {"value": "3.50", "currency": "USD"}}
    ],
    "categories": [{"categoryName": "Health & Beauty"}],
}

_SAMPLE_ITEM_NO_IMAGE = {
    "itemId": "v1|999000000001|0",
    "title": "Test Product No Image",
    "itemWebUrl": "https://www.ebay.com/itm/999000000001",
    "price": {"value": "19.99", "currency": "USD"},
    # "image" key absent entirely
}

_SAMPLE_ITEM_NO_ITEM_ID = {
    "title": "Test Product No ItemId",
    "itemWebUrl": "https://www.ebay.com/itm/000000000000",
    "price": {"value": "9.99", "currency": "USD"},
    "image": {"imageUrl": "https://i.ebayimg.com/images/g/xyz/s-l225.jpg"},
    # "itemId" key absent
}
```

### Required test cases

**Class: TestEbayItemToRaw**

| Test | Input | Expected |
|---|---|---|
| `test_item_id_extracted` | `_SAMPLE_ITEM` | `raw["item_id"] == "v1|158043884007|0"` |
| `test_image_url_extracted` | `_SAMPLE_ITEM` | `raw["image_url"] == "https://i.ebayimg.com/images/g/abc/s-l225.jpg"` |
| `test_source_url_field_unchanged` | `_SAMPLE_ITEM` | `raw["item_url"] == "https://www.ebay.com/itm/158043884007?hash=abc"` |
| `test_price_extracted` | `_SAMPLE_ITEM` | `raw["price"] == 24.99` |
| `test_shipping_cost_extracted` | `_SAMPLE_ITEM` | `raw["shipping_cost"] == 3.5` |
| `test_supplier_cost_is_none` | `_SAMPLE_ITEM` | `raw["supplier_cost"] is None` |
| `test_missing_image_returns_none` | `_SAMPLE_ITEM_NO_IMAGE` | `raw["image_url"] is None` (no crash) |
| `test_missing_item_id_returns_none` | `_SAMPLE_ITEM_NO_ITEM_ID` | `raw["item_id"] is None` (no crash) |

**Class: TestNormalizeCandidate (eBay path)**

| Test | Input | Expected |
|---|---|---|
| `test_item_id_passes_through` | `raw` from `_SAMPLE_ITEM` | `candidate["item_id"] == "v1|158043884007|0"` |
| `test_image_url_passes_through` | `raw` from `_SAMPLE_ITEM` | `candidate["image_url"] == "https://i.ebayimg.com/images/g/abc/s-l225.jpg"` |
| `test_source_url_mapped_from_item_url` | `raw` from `_SAMPLE_ITEM` | `candidate["source_url"] == "https://www.ebay.com/itm/158043884007?hash=abc"` |
| `test_retail_price_mapped` | `raw` from `_SAMPLE_ITEM` | `candidate["retail_price"] == 24.99` |
| `test_supplier_cost_is_none` | `raw` from `_SAMPLE_ITEM` | `candidate["supplier_cost"] is None` |
| `test_missing_image_item_id_none_no_crash` | `raw` from `_SAMPLE_ITEM_NO_IMAGE` | `candidate["image_url"] is None` |
| `test_missing_item_id_none_no_crash` | `raw` from `_SAMPLE_ITEM_NO_ITEM_ID` | `candidate["item_id"] is None` |

**Class: TestEndToEndCandidatePipeline** (optional, higher confidence)

Run `_ebay_item_to_raw()` -> `_normalize_candidate()` -> `normalize_candidate()` in sequence
and assert that the final normalized candidate has:
- `item_id == "v1|158043884007|0"`
- `image_url == "https://i.ebayimg.com/images/g/abc/s-l225.jpg"`
- `source_url == "https://www.ebay.com/itm/158043884007?hash=abc"`
- `retail_price == 24.99`
- `supplier_cost is None`

No DB call, no HTTP call, no env read in any test.

---

## 6. Existing DB Rows

This fix applies only to future eBay discoveries. The existing 37 eBay rows in `products.db`
are NOT updated by this code change.

### Why existing rows are unaffected

`upsert_discovered_candidate()` in `db.py` is INSERT-only. When re-discovery is run after
the fix, the dedup check (`source + source_url`) matches each of the 37 existing rows and
returns `{"inserted": False, "reason": "duplicate_url"}` without any UPDATE.

### Separate backfill phases (not part of this plan)

**item_id backfill (no API call required):**
- All 37 eBay rows have `source_url` set.
- The eBay item ID is embedded in the URL: `https://www.ebay.com/itm/{itemId}?...`
- A targeted SQL UPDATE script can extract item_id using regex on source_url:
  `re.search(r'/itm/(\d+)', source_url)` -> group(1)
- Safety guard: `WHERE source='ebay' AND item_id IS NULL AND source_url IS NOT NULL`
- Must validate extracted ID (digits only, reasonable length) before writing.
- Requires explicit owner approval before running.

**image_url backfill (API call required, deferred):**
- No image data is stored locally for existing eBay rows.
- Recovery requires: (a) eBay item detail API call per item_id, or (b) re-running discovery
  with a modified upsert that adds an UPDATE path for rows with NULL image_url.
- Neither option is part of this plan. Both require separate approval.
- Status: DEFERRED until item_id backfill is complete and owner approves next phase.

---

## 7. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `item["image"]` is absent or not a dict in some eBay responses | Possible | Use `(item.get("image") or {}).get("imageUrl")` — safe for all cases |
| `itemId` key absent in some response items | Unlikely but possible | Use `item.get("itemId")` — returns None, not a crash |
| `itemId` format varies (`"v1|...|0"` vs plain number) | Possible | Do not parse itemId; store as-is; dedup and backfill logic handles both |
| Dedup on `source + item_id` fires before `source + source_url` for re-discovered items | Not applicable yet — all existing rows have `item_id=NULL`, so dedup #2 never fires | After backfill, dedup order matters; existing plan already handles this |
| Fix introduces behavioral regression for other fields | Low | Only 4 lines added; all other field mappings untouched and covered by tests |
| Re-discovery after fix still returns `duplicate_url` for existing rows | Confirmed | Expected behavior; backfill is the solution, not connector fix alone |
| eBay connector freeze rule violated | Applicable | No implementation without explicit owner approval; this is a plan doc only |

---

## 8. Safety Guardrails

All of the following constraints apply during implementation when approved:

- No discovery endpoint called during implementation or testing.
- No external API calls — tests use inline sample dicts only.
- No DB writes — implementation only changes connector field mapping; no `db.py` touched.
- No DB schema changes — `item_id` and `image_url` columns already exist.
- No changes to `decision_engine.py`, `scoring.py`, or `main.py`.
- No changes to CJ, TikTok, Google, YouTube, or Meta connectors.
- No changes to frontend.
- No changes to `normalize_candidate()` in `sources/normalize.py` — it already reads
  `item_id` and `image_url` correctly.
- No changes to `upsert_discovered_candidate()` in `db.py` — it already persists correctly.
- `backend/.env` must not be modified or printed.
- Commit must pass: py_compile, unittest, secret scan, mojibake check.

---

## 9. Acceptance Criteria

Implementation phase is complete only when all of the following are true:

| Criterion | Check |
|---|---|
| `py_compile backend/sources/ebay.py backend/test_ebay_metadata_mapping.py` passes | Required |
| `python -m unittest test_ebay_metadata_mapping` passes with 0 failures | Required |
| No secrets in any modified file (grep scan passes) | Required |
| No mojibake in any modified file (grep scan passes) | Required |
| `git diff backend/sources/ebay.py` shows exactly 4 lines added, 0 removed | Required |
| `git diff` shows no changes to `db.py`, `main.py`, `decision_engine.py`, `scoring.py` | Required |
| `git diff` shows no changes to any CJ/TikTok/Google/YouTube/Meta connector | Required |
| After future eBay discovery: new rows have `item_id` and `image_url` populated | Verified by smoke test |
| Existing 37 eBay rows: `item_id` and `image_url` remain NULL (no silent backfill) | Verified by DB query |

---

## 10. Recommended Next Command

**NOT APPROVED UNTIL OWNER SAYS IMPLEMENT.**

When approved, the implementation sequence would be:

```
# Step 1: Implement connector fix (4 lines in sources/ebay.py)
# Step 2: Create test file (backend/test_ebay_metadata_mapping.py)
# Step 3: Verify
cd backend
python -m py_compile sources/ebay.py test_ebay_metadata_mapping.py
python -m unittest test_ebay_metadata_mapping -v
cd ..
git diff --stat backend/sources/ebay.py backend/test_ebay_metadata_mapping.py
grep -Ein "(api[_ -]?key|secret|token)[[:space:]]*=[[:space:]]*[A-Za-z0-9_\-]{8,}" backend/sources/ebay.py backend/test_ebay_metadata_mapping.py || true
python - <<'PY'
from pathlib import Path
files = ["backend/sources/ebay.py", "backend/test_ebay_metadata_mapping.py"]
bad = False
for f in files:
    data = Path(f).read_bytes()
    if b"\xc3\xa2" in data:
        print(f"{f}: contains mojibake byte pattern C3 A2")
        bad = True
if not bad:
    print("mojibake byte-pattern check: clean")
PY
# Step 4: Await owner review before commit
```

Owner must explicitly approve before any of the above runs.

---

## 11. DB Backfill — Separate Phase (Not Part of This Plan)

| Backfill phase | Depends on | Requires API | Status |
|---|---|---|---|
| item_id from source_url (37 eBay rows) | This plan approved + implemented | No | Not approved |
| image_url for existing rows | item_id backfill complete + owner approval | Yes (eBay item detail) | Not started |
| Update dedup to allow NULL-field updates | Owner decision | No | Not designed |

The item_id backfill is documented in EBAY_IMAGE_PIPELINE_AUDIT.md section 9 Option B.
It is a safe, no-API-call operation but must be planned, tested, and approved separately.
