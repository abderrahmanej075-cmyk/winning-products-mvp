# CHECKPOINT: CJ Dropshipping — Live + Active

Date: 2026-07-05

## Current status: active — live_call_confirmed = true

CJ Dropshipping connector is live. Token is set, real API calls have been verified,
and the connector has auto-promoted to `active`. Products are persisted to the DB.

---

## Verification results (2026-07-05)

| Check | Result |
|---|---|
| `POST /sources/cj_dropshipping/verify` | `live_call_success=true`, `candidates_returned=3` |
| Connector status | `active` |
| `cj_mode` | `confirmed` |
| `/discovery/multisource` source_breakdown | `{cj_dropshipping: 5}` (not stub) |
| `source_info.cj_dropshipping.data_mode` | `live` |
| `source_info.cj_dropshipping.persisted` | `true` |
| `db_save` | `{inserted: 5, skipped_duplicate: 0}` |
| `/products` | 5 rows with `source=cj_dropshipping` |
| `/export/products?filter=all&format=json` | 5 CJ products included |

---

## API audit result (2026-07-05)

| Check | Original implementation | After audit | Verdict |
|---|---|---|---|
| Base URL | `https://developers.cjdropshipping.com/api2.0` | unchanged | CORRECT |
| Auth header | `CJ-Access-Token: {token}` | unchanged | CORRECT |
| Search endpoint | `GET /v1/product/query` (ID lookup — wrong) | `GET /v1/product/list` | FIXED |
| Pagination params | `productNameEn`, `pageNum`, `pageSize` | unchanged | CORRECT |
| Response envelope | `data.list` | unchanged | CORRECT |
| `productNameEn`, `pid`, `categoryName`, `productWeight` | mapped | unchanged | CORRECT |
| `sellPrice` | mapped as `retail_price` | remapped to `supplier_cost` (confirmed live) | FIXED |
| `productImage` | not mapped | mapped to `image_url` (confirmed available) | ADDED |
| `sourcePrice` (supplier cost) | mapped | **removed — field does not exist in any CJ endpoint** | FIXED |
| `productUrl` / `productDetailUrl` | mapped as source_url | **removed — not returned by CJ API** | FIXED |

---

## Known CJ API field limitations — confirmed from live responses

### Available in live mode (from `/v1/product/list`)

| CJ field | Maps to | Notes |
|---|---|---|
| `productNameEn` | `name` | English product title |
| `productImage` | `image_url` | Product image URL (confirmed in list response) |
| `pid` | `item_id` | Used for dedup and secondary lookups |
| `categoryName` | `category` | Category string |
| `sellPrice` | `supplier_cost` | **Confirmed: price CJ charges the dropshipper** (see interpretation below) |
| `productWeight` (grams) | `product_weight_kg` | Converted: grams / 1000 |

### NOT available from `/v1/product/list`

| Field | Status |
|---|---|
| `suggestSellPrice` (retail range) | **List endpoint only — available from `/v1/product/query` detail, not list** |
| `sourcePrice` / supplier cost | **Does not exist in CJ API v2.0** — confirmed |
| `productUrl` / `productDetailUrl` | **Not returned by CJ API** — confirmed |
| `retail_price` | **None in live discovery mode** — requires detail endpoint enrichment |
| Shipping cost | Requires separate logistics endpoint (see Phase 2 below) |

### `sellPrice` interpretation — RESOLVED (2026-07-05)

Live API confirmation from `GET /v1/product/query?pid=2606290802201632600`:

```
sellPrice:        "19.50"
suggestSellPrice: "132.02 - 212.85"
variantSellPrice: 19.5
```

**`sellPrice` = what CJ charges the dropshipper per unit = `supplier_cost`.**

`suggestSellPrice` is CJ's suggested retail range (string, not available in list endpoint).
CJ's suggested retail may not reflect actual market price — validate against eBay/Amazon data.

**Current mapping:**
- `supplier_cost = sellPrice` (confirmed)
- `retail_price = None` (suggestSellPrice not in list endpoint)
- Margin scoring is not possible until retail price is populated from another source

### Impact on scoring

- `supplier_cost` populated from `sellPrice` (live mode, confirmed)
- `retail_price` will be `None` in live mode — margin/profit scoring unavailable
- `image_url` populated from `productImage` (live mode)
- `source_url` will be `None` in live mode — no clickable product link
- Scoring confidence remains reduced until retail price enrichment is added

---

## Confirmed CJ API secondary endpoints (from research, 2026-07-05)

### Product detail by PID

```
GET /v1/product/query?pid={pid}
CJ-Access-Token: {token}
```

Returns: `pid`, `productNameEn`, `sellPrice`, `suggestSellPrice` (range string),
`variants[]` (with `vid`, `variantSku`, `variantSellPrice`, `variantSugSellPrice`,
`inventories[]`), `status`

**No supplier cost / source price returned. `suggestSellPrice` is a range string.**

### Variant / SKU details

```
GET /v1/product/variant/query?pid={pid}
CJ-Access-Token: {token}
```

Per variant: `vid`, `variantNameEn`, `variantSku`, `variantWeight`, `variantSellPrice`,
`variantSugSellPrice`, `variantLength`, `variantWidth`, `variantHeight`

Also: `GET /v1/product/variant/queryByVid?vid={vid}` — single variant + inventory breakdown.

### Inventory / warehouse stock

```
GET /v1/product/stock/getInventoryByPid?pid={pid}
GET /v1/product/stock/queryByVid?vid={vid}
CJ-Access-Token: {token}
```

Returns: `totalInventoryNum`, `cjInventoryNum`, per warehouse. **Price fields: none.**

### Shipping cost — `POST /v1/logistic/freightCalculate`

```
POST /v1/logistic/freightCalculate
CJ-Access-Token: {token}
Content-Type: application/json

{
  "startCountryCode": "CN",
  "endCountryCode": "US",
  "products": [{ "vid": "{variant_id}", "quantity": 1 }]
}
```

**Requires `vid` (variant ID), not `pid`.** Flow: pid → variant query → vid → freight calculate.

Returns: `logisticName`, `logisticPrice` (USD), `logisticAging`, `totalPostageFee`.

Also: `POST /v1/logistic/freightCalculateTip` — weight/volume based, no vid required.

---

## Token lifecycle — per current CJ docs (2026-07-05)

| Token | TTL |
|---|---|
| Access Token | **180 days** (per current CJ docs page — previous 15-day value is obsolete) |
| Refresh Token | **180 days** |

> **Note:** An earlier version of CJ docs stated 15 days. The current CJ docs page
> visible as of 2026-07-05 states: "the life of an access-token is 180 days, and
> the life of a refresh-token is 180 days." All references to 15-day TTL have been
> updated across this project.

### First-time token capture (safe local script)

**SECURITY: Never paste your API Key, access token, or refresh token into chat with an AI assistant.**

**Option A — Windows clipboard (recommended):**
1. Open CJ Dropshipping dashboard → Account → Open API → copy your API Key
2. From `backend/` directory, run:

```
python -m dotenv -f .env run -- python scripts/get_cj_tokens_from_api_key.py
```

The script reads the key directly from the clipboard via PowerShell Get-Clipboard.

**Option B — environment variable:**
```powershell
# PowerShell (from backend/ directory):
$env:CJ_API_KEY_TEMP="<paste_key_here_in_terminal_only>"
python scripts/get_cj_tokens_from_api_key.py
```

**Check availability first (no API call made):**
```
python scripts/get_cj_tokens_from_api_key.py --check
```

This script:
- Tries `CJ_API_KEY_TEMP` first, then Windows clipboard if env var is absent
- Calls `POST /v1/authentication/getAccessToken` with your API Key
- Writes `CJ_API_TOKEN`, `CJ_REFRESH_TOKEN`, `CJ_TOKEN_EXPIRES_AT`, `CJ_REFRESH_TOKEN_EXPIRES_AT` to `backend/.env`
- Never prints key or token values — prints only `access_token_saved=true`, `refresh_token_saved=true`, timestamps
- Restart the backend after running

**Note:** Calling `getAccessToken` within 24 hours of a previous call returns the same cached
token. A new token is only issued after 24 hours or after explicit logout.

### Refresh (safe local script — run before expiry)

```
# From project root, with .env loaded:
python -m dotenv -f backend/.env run -- python backend/scripts/refresh_cj_token.py
# Or from backend/ directory:
python -m dotenv -f .env run -- python scripts/refresh_cj_token.py
```

This script:
- Reads `CJ_REFRESH_TOKEN` from the injected environment
- Calls `POST /v1/authentication/refreshAccessToken`
- Updates `CJ_API_TOKEN` (and `CJ_REFRESH_TOKEN` if rotated) in `backend/.env`
- Updates `CJ_TOKEN_EXPIRES_AT` and `CJ_REFRESH_TOKEN_EXPIRES_AT`
- Never prints token values — prints only `access_token_updated=true`, timestamps
- Restart the backend after running

### Current token status (2026-07-06)

| Variable | Status |
|---|---|
| `CJ_API_TOKEN` | **Set** — connector active |
| `CJ_REFRESH_TOKEN` | **Missing** — must be added to enable future refresh |
| `CJ_TOKEN_EXPIRES_AT` | Not set — will be written by `get_cj_tokens_from_api_key.py` |

**Action required:** To enable future token refresh without re-entering the API Key, run
`get_cj_tokens_from_api_key.py` once (it will re-capture the current cached token and
write `CJ_REFRESH_TOKEN`). Do this before your current token expires (~180 days from when
it was first generated).

### env vars for token lifecycle

```
CJ_API_TOKEN=                      # Access Token (180-day TTL)
CJ_REFRESH_TOKEN=                  # Refresh Token (180-day TTL)
CJ_TOKEN_EXPIRES_AT=               # ISO datetime — when access token expires
CJ_REFRESH_TOKEN_EXPIRES_AT=       # ISO datetime — when refresh token expires
```

---

## Future integration path for full margin scoring

### Phase 1 — Discovery only (current, live)
- `GET /v1/product/list` → name, pid, image_url, category, supplier_cost (sellPrice), weight
- `retail_price` = None (not available from list endpoint)
- `source_url` = None (not available)
- Margin scoring requires retail price from another source (eBay, manual, etc.)

### Phase 2 — Retail price enrichment (next)
- Option A: Call `GET /v1/product/query?pid=` per live product → get `suggestSellPrice`
  Parse range string lower bound as `retail_price`. Note: CJ's suggested retail may
  be inflated — validate against market data before using for scoring.
- Option B: Cross-reference by product name against eBay/Amazon results already in DB.

### Phase 3 — Shipping cost integration
- Per live product: `GET /v1/product/variant/query?pid=` → get `vid`
- Then: `POST /v1/logistic/freightCalculate` with `vid`, `quantity=1`, destination country
- `shipping_cost` = `logisticPrice` from response
- Full margin scoring: `retail_price - supplier_cost - shipping_cost`

---

## Health state progression (automatic, never manual)

```
stub_only        CJ_API_TOKEN absent
live_configured  token set, POST /sources/cj_dropshipping/verify not yet run
live_untested    verify ran but call failed or no candidates returned
active           verify succeeded — auto-promoted via flag file  ← CURRENT STATE
```

---

## Files changed in this connector

| File | Change |
|---|---|
| backend/sources/cj_dropshipping.py | Collector + stub; endpoint fixed; flag file helpers; sellPrice→supplier_cost confirmed; image_url added; TTL 180 days |
| backend/.cj_dropshipping_live_confirmed.json | Runtime flag (gitignored) |
| backend/sources/connectors/__init__.py | CjConnector — 4-state status; TTL 180 days; sellPrice interpretation updated |
| backend/main.py | POST /sources/cj_dropshipping/verify endpoint |
| backend/.env.example | CJ_API_TOKEN docs updated; TTL 180 days; sellPrice interpretation noted |
| backend/db.py | item_id column added to migration + INSERT (fixed silent save bug) |
| .gitignore | backend/.cj_dropshipping_live_confirmed.json |
| CHECKPOINT_CJ_DROPSHIPPING.md | This file — full status update |

---

## Freeze rules

- eBay: live, complete, frozen — do not modify
- TikTok Ads: pending_access — do not touch until TikTok Developer Support responds
- CJ Dropshipping: active, live — maintenance only; no new connector work yet
- Google Trends / Amazon / AliExpress / Reddit / YouTube / Meta: all paused

---

## Completion criteria

### Current scope — discovery phase (complete)
- [x] CJ_API_TOKEN set (Access Token)
- [x] POST /sources/cj_dropshipping/verify returns `live_call_confirmed=true`
- [x] Connector status = `active` (auto-promoted)
- [x] source_breakdown shows `{cj_dropshipping: N}` (not `cj_dropshipping_stub`)
- [x] db_save.inserted > 0
- [x] /products shows `source=cj_dropshipping` products
- [x] /export/products includes `cj_dropshipping` products
- [x] `sellPrice` interpretation resolved: `sellPrice` = supplier_cost (confirmed)
- [x] `image_url` from `productImage` (confirmed available in list endpoint)

### Full margin scoring — future phase
- [ ] Discovery criteria complete ✓
- [ ] `retail_price` enrichment added (Phase 2: detail endpoint or cross-source)
- [ ] `shipping_cost` populated from live CJ logistics API (Phase 3)
- [ ] Net profit scoring enabled for CJ products
