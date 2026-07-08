# eBay image_url + item_id Pipeline Audit

Created: 2026-07-08
Status: audit_complete / pending_owner_review / no_code_change

---

## 1. Executive Summary

Root cause confirmed: **Category A** — the eBay connector (`sources/ebay.py`) never
extracts `itemId` or `image.imageUrl` from the eBay Browse API response. Both fields
are available in the API response but are not mapped in `_ebay_item_to_raw()`.

The database persistence layer (`db.py:upsert_discovered_candidate`) and the shared
normalization layer (`sources/normalize.py:normalize_candidate`) are correct and would
persist `item_id` and `image_url` if they arrived from the connector. The gap is
exclusively in `sources/ebay.py`.

A secondary factor is that `upsert_discovered_candidate()` is INSERT-only with no UPDATE
path. Even after fixing the connector, re-running discovery would not update the existing
37 eBay rows because the dedup check matches on `source + source_url` (which is already
populated) and returns `duplicate_url` without touching the existing row.

Two distinct fixes are therefore required:
1. Fix the connector mapping (affects future discoveries only).
2. Backfill existing 37 eBay rows (separate targeted operation).

`item_id` can be safely backfilled for all 37 existing rows without any external API call
because the eBay item ID is embedded in the already-stored `source_url`
(e.g. `https://www.ebay.com/itm/158043884007?...` → item_id = `158043884007`).

`image_url` cannot be recovered for existing rows without re-fetching from the eBay API.

---

## 2. Files Inspected

| File | Purpose | Finding |
|---|---|---|
| `backend/sources/ebay.py` | eBay Browse API HTTP client + field mapping | `_ebay_item_to_raw()` does not extract `itemId` or `image.imageUrl` |
| `backend/sources/connectors/ebay_official.py` | Production gate + connector wrapper | Delegates to `EbayCollector` from `sources/ebay.py`; no additional field mapping |
| `backend/sources/normalize.py` | Shared multi-source normalization | Correctly reads `item_id` and `image_url` from candidate dict; not the source of the gap |
| `backend/db.py` | DB persistence | `upsert_discovered_candidate()` correctly persists `item_id` and `image_url`; INSERT-only, no UPDATE path |
| `backend/products.db` | Live SQLite database | 37 eBay rows: source_url SET on all, item_id NULL on all, image_url NULL on all |

---

## 3. Current DB Evidence

```
Source         | Total | image_url SET | item_id SET | source_url SET | supplier_cost SET | shipping SET
None/manual    |    34 |             0 |           0 |              0 |                31 |           34
ebay           |    37 |             0 |           0 |             37 |                 0 |            0
cj_dropshipping|     5 |             5 |           5 |              0 |                 5 |            0
```

Key observations:

- eBay has `source_url` = 37/37. The `itemWebUrl` field IS being extracted and persisted.
  This confirms the connector-to-DB pipeline is working for fields that are mapped.

- eBay has `image_url` = 0/37 and `item_id` = 0/37. These fields are never populated.
  The only difference from `source_url` is that they are not mapped in `_ebay_item_to_raw()`.

- CJ has `image_url` = 5/5 and `item_id` = 5/5. CJ is the reference implementation.
  CJ maps `productImage` → `image_url` and its own PID → `item_id` at discovery time.

- eBay `source_url` values contain the item ID in the URL path:
  `https://www.ebay.com/itm/158043884007?...` → item_id extractable without any API call.

- Earliest eBay row discovered_at: `2026-07-01T16:32:18` — these are not ancient records.
  They were inserted when the eBay connector was already live in production, but the
  connector mapping was incomplete at that time.

---

## 4. Connector Mapping Evidence

### `_ebay_item_to_raw()` in `sources/ebay.py` (line 134)

This function maps a raw eBay `item_summary` dict to an intermediate raw dict:

```python
return {
    "title": item.get("title", "").strip(),
    "category": category,
    "country": country,
    "item_url": item.get("itemWebUrl"),     # <-- listing URL, correctly extracted
    "price": price,                          # <-- item.price.value, correctly extracted
    "supplier_cost": None,                   # explicitly None (no supplier cost from eBay)
    "shipping_cost": shipping,               # shippingOptions[0].shippingCost.value
    "weight_kg": None,                       # not available from search endpoint
    # ... signal fields all None ...
    # MISSING: item.get("itemId") -> not extracted
    # MISSING: item.get("image", {}).get("imageUrl") -> not extracted
}
```

The eBay Browse API `item_summary/search` response includes:
- `itemId` (string) — the eBay item identifier
- `image.imageUrl` (string) — primary product image URL
- `itemWebUrl` (string) — listing URL (this one IS extracted)

Neither `itemId` nor `image.imageUrl` are read from the `item` dict.

### `_normalize_candidate()` in `sources/ebay.py` (line 101)

This function maps the intermediate raw dict to scoring-field-named keys:

```python
return {
    "name": raw.get("title", "").strip(),
    "source_url": raw.get("source_url") or raw.get("item_url") or ...,  # item_url -> source_url: OK
    "retail_price": raw.get("price"),
    "supplier_cost": raw.get("supplier_cost"),
    "shipping_cost": raw.get("shipping_cost"),
    "product_weight_kg": raw.get("weight_kg"),
    # ... signal fields ...
    # NO "item_id" key — never set, so candidate["item_id"] is absent
    # NO "image_url" key — never set, so candidate["image_url"] is absent
}
```

Result: the candidate dict passed downstream has no `item_id` or `image_url` key.

### `shipping_cost` also absent

`_ebay_item_to_raw()` attempts to extract shipping from `shippingOptions[0].shippingCost`:

```python
shipping_opts = item.get("shippingOptions", [])
if shipping_opts:
    shipping = float(shipping_opts[0].get("shippingCost", {}).get("value", ""))
```

The eBay Browse API `item_summary/search` endpoint does not return `shippingOptions`
reliably for all items. When the field is absent, `shipping` remains `None`. This explains
why all 37 eBay rows have `shipping_cost = NULL` despite the extraction attempt.
This is a data availability gap in the search endpoint, not a code bug.

---

## 5. Normalize Evidence

`normalize_candidate()` in `sources/normalize.py` (line 107):

```python
return {
    ...
    "item_id": p.get("item_id"),     # reads item_id — would work if connector set it
    "image_url": p.get("image_url"), # reads image_url — would work if connector set it
    ...
}
```

This function is correct. It would propagate `item_id` and `image_url` from the candidate
dict if they were present. Since the eBay `_normalize_candidate()` never sets these keys,
`p.get("item_id")` and `p.get("image_url")` both return `None`.

No gap in `sources/normalize.py`.

---

## 6. DB Persistence Evidence

`upsert_discovered_candidate()` in `db.py` (line 378):

```python
INSERT INTO products (name, category, country, source, source_url,
    item_id, image_url, retail_price, supplier_cost, shipping_cost, ...)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ...)
```

with values:
```python
(candidate.get("item_id") or "").strip() or None,
candidate.get("image_url") or None,
```

The INSERT is correct. `item_id` and `image_url` are included in the column list and
values tuple. If the candidate dict had these fields populated, they would be stored.

**Dedup / UPDATE behavior:**

The function has THREE dedup checks, all read-then-skip:
1. `source + source_url` → match → return existing row ID, no INSERT, no UPDATE
2. `source + item_id` → match → return existing row ID, no INSERT, no UPDATE
3. `source + normalized name` → match → return existing row ID, no INSERT, no UPDATE

If a match is found, `upsert_discovered_candidate()` returns `{"inserted": False, ...}`
and does NOT modify the existing row in any way. There is no UPDATE path.

Consequence: if discovery is re-run after fixing the connector, the dedup check on
`source + source_url` will match the existing 37 eBay rows (source_url is already set)
and return them unchanged. The existing rows with `item_id=NULL` and `image_url=NULL`
will not be updated by re-running discovery alone.

---

## 7. Root Cause

**Primary: Category A — eBay connector never extracted `image_url` or `item_id`**

`_ebay_item_to_raw()` in `sources/ebay.py` does not include `itemId` or
`image.imageUrl` in its return dict. The eBay Browse API returns both fields in
`item_summary` objects but they are silently dropped.

**Secondary: Category D — dedup logic preserves old rows with NULL values**

`upsert_discovered_candidate()` is INSERT-only. Discovering the same eBay item again
(even with a fixed connector) will hit the `source + source_url` dedup check and return
the existing row unchanged. Existing `item_id=NULL` and `image_url=NULL` rows will persist.

**NOT a cause:**
- `sources/normalize.py` — correct, reads item_id and image_url if present
- `db.py` INSERT — correct, persists item_id and image_url if present
- eBay API response — eBay does return itemId and image.imageUrl in search results
- Database schema — both columns exist and are nullable TEXT

---

## 8. What Is Confirmed vs Unknown

### Confirmed

- `_ebay_item_to_raw()` does not extract `itemId` or `image.imageUrl` — confirmed by code read
- `source_url` is populated (37/37) — confirms the connector pipeline works end-to-end for mapped fields
- `item_id` and `image_url` are both NULL (37/37) — confirmed by DB query
- `upsert_discovered_candidate()` is INSERT-only — confirmed by code read
- Item ID is embedded in `source_url` for all 37 eBay rows — confirmed by DB query
  (URL pattern: `https://www.ebay.com/itm/{itemId}?...`)
- CJ connector correctly maps `productImage` → `image_url` and pid → `item_id` — reference implementation

### Unknown (would require API call or re-discovery to confirm)

- Whether `image.imageUrl` is present in eBay search API responses for these specific items
  (highly likely based on eBay API docs, but not verified for these exact items)
- Whether the items are still listed on eBay (listings expire)
- Whether eBay `shippingOptions` is reliably present in search results (probably not —
  `shipping_cost = NULL` on all 37 eBay rows suggests the field is absent from search results)

---

## 9. Fix Options

### Option A — Code-only mapping fix for future eBay discoveries

**What:** Add `itemId` and `image.imageUrl` extraction to `_ebay_item_to_raw()`.
Add `"item_id"` and `"image_url"` keys to `_normalize_candidate()` in `sources/ebay.py`.

```python
# In _ebay_item_to_raw():
"item_id": item.get("itemId"),
"image_url": item.get("image", {}).get("imageUrl"),
# or: item.get("thumbnailImages", [{}])[0].get("imageUrl") as fallback
```

```python
# In _normalize_candidate():
"item_id": raw.get("item_id"),
"image_url": raw.get("image_url"),
```

**Scope:** Affects only NEW eBay discoveries going forward. Existing 37 rows unchanged.

**Pros:**
- Minimal code change (2 lines in `_ebay_item_to_raw()`, 2 lines in `_normalize_candidate()`)
- No DB migration, no schema change
- No backfill risk
- Correct fix at the root cause level

**Cons:**
- Existing 37 eBay rows remain with `item_id=NULL` and `image_url=NULL`
- NEEDS_ENRICHMENT status on existing rows unchanged
- Only helps if more eBay discoveries are run after the fix

**Risk:** Low. Pure addition, no behavior change for CJ or other sources.

---

### Option B — Safe item_id backfill from source_url (no API call)

**What:** For each eBay row with `item_id IS NULL` and `source_url IS NOT NULL`,
extract the item ID from the source_url using a regex:
`re.search(r'/itm/(\d+)', source_url)` → group(1) is the item ID.

Update `item_id` in-place for these rows.

**Scope:** All 37 existing eBay rows. No external API call required.

**Pros:**
- Recovers item_id for all 37 existing eBay rows immediately
- No external API call — uses already-stored data
- Low risk — source_url already confirmed to contain item ID for all 37 rows
- Enables dedup check #2 (source + item_id) for future discoveries
- Enables CJ/supplier lookup if future supplier-matching logic uses item_id as key

**Cons:**
- Requires a DB write — needs careful targeted script (WHERE source='ebay' AND item_id IS NULL)
- Does NOT recover image_url — that still needs an API call
- item_id format must be validated before write (regex sanity check)

**Risk:** Low-medium. A targeted UPDATE with WHERE guards is safe, but any DB write
requires a backup or rollback plan. Must not overwrite existing non-NULL item_id values.

---

### Option C — Re-run eBay discovery after connector fix

**What:** Fix the connector (Option A), then run `/discovery/multisource` or
`/sources/ebay/discover` to re-discover eBay products. Expect new rows to have
`item_id` and `image_url` populated.

**Scope:** Creates NEW rows for newly discovered products. Existing 37 rows UNCHANGED.

**Why existing rows are NOT updated:** `upsert_discovered_candidate()` dedup check #1
(`source + source_url`) will match all 37 existing rows and return `{"inserted": False}`.
The existing rows are not touched.

Unless the upsert logic is modified to perform an UPDATE when `image_url IS NULL` on an
existing row (a conditional update path), re-discovery does not help existing rows.

**Pros:**
- No DB backfill script needed
- Any new seeds/searches would produce enriched rows going forward
- Natural refresh over time

**Cons:**
- Existing 37 rows permanently stuck with NULL image_url unless upsert is modified
- Adds duplicate-like rows (same products but new variants from new search results)
- No guarantee re-discovery finds the same products (eBay listings expire or change)

**Risk:** Medium. Requires connector code change + a discovery run. Existing rows unaffected.

---

### Option D — Ignore old rows, fix forward only

**What:** Fix the connector mapping (Option A) and accept that the existing 37 rows will
remain in NEEDS_ENRICHMENT. No backfill. Over time, new discoveries replace or supplement
the old rows.

**Scope:** No DB changes. Only connector code fix.

**Pros:**
- Simplest path
- No backfill risk
- Existing rows are still valid data points (retail_price, score, recommendation)

**Cons:**
- 37 existing live eBay records permanently stuck at NEEDS_ENRICHMENT due to image_url
- Decision engine cannot promote them beyond NEEDS_ENRICHMENT
- Wastes the existing DB records

**Risk:** Lowest. Pure code fix with no DB touch.

---

## 10. Recommendation (Ranked by ROI, Evidence-Only)

**1. Option A first — fix the connector mapping (code-only, no DB touch)**
   This is the correct root cause fix and costs 4 lines of code. Must be done before
   any discovery re-run or backfill attempt. Risk is minimal.

**2. Option B second — backfill item_id from source_url for existing 37 eBay rows**
   item_id is recoverable from source_url without any external API call. A targeted,
   guarded SQL UPDATE (`WHERE source='ebay' AND item_id IS NULL AND source_url IS NOT NULL`)
   with a regex extraction script is safe and recovers a useful field.
   Requires owner approval and a tested backfill script before running.

**3. image_url for existing rows — deferred**
   No safe path to recover image_url for existing rows without an eBay API call per item.
   Options: targeted eBay item search by item_id (after Option B), or accept NULL and
   wait for re-discovery (which requires modifying the upsert UPDATE path).
   Plan this as a Phase 2 backfill after Options A and B are done.

**4. Option C (re-run discovery) — conditional**
   Only useful after Option A is applied. Will produce new enriched rows for new
   search results but will not update existing rows. May be combined with a dedup
   logic update (add UPDATE path when existing row has NULL image_url).

**Do not implement any option until explicitly approved.** This document is analysis only.

---

## 11. Safety Rules for Any Fix

- Do not modify eBay connector without reading the full diff against MASTER_PROJECT_STATUS.md
  freeze rules (eBay is FROZEN - do not modify unless blocking production bug).
- Any DB backfill script must:
  - Use `WHERE source='ebay' AND item_id IS NULL` guards
  - Validate item_id format (digits only, 10-15 chars) before writing
  - Never overwrite non-NULL item_id values
  - Be run on a test query first (SELECT, not UPDATE) to confirm row count
  - Require owner sign-off before execution
- No connector changes without a targeted plan separate from this audit.
- No live eBay API calls without explicit approval.
- No DB schema changes (both item_id and image_url columns already exist).
