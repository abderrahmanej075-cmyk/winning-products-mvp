# Source Strategy Map

Last updated: 2026-07-07

---

## Core philosophy

1. **Audit many sources.** Research and document every candidate API before touching code.
2. **Implement one source at a time.** No parallel implementation work. One connector reaches `closed` before the next starts.
3. **Verify live data.** No connector is considered active until a real API call is confirmed and real data is saved (where applicable).
4. **Freeze when closed.** A connector that is live and complete is frozen. It does not change unless a specific, named phase (Phase 2, Phase 3) is scheduled.
5. **Move to the next source only after explicit owner decision.** Completing an audit does not authorize implementation. The project owner must approve the next step before any code is written.

---

## Stage definitions

| Stage | Meaning |
|---|---|
| `idea` | Source identified as potentially useful. No research done yet. No API confirmed. |
| `official_audit` | Official API or access path researched from public/official documentation. Coverage, limitations, access requirements, and data value documented. No code written, no credentials obtained. |
| `pending_setup` | Official API confirmed. Access requirements known. Waiting for developer app creation, account verification, or token generation before a live call can be attempted. |
| `pending_access` | Setup complete but access is gated by third-party approval (invitation, review, support ticket). Waiting for external party to grant access. |
| `active` | Live call confirmed. Real data returned and (where applicable) saved to DB. Connector auto-promoted after verify endpoint success. |
| `closed` | Active and complete for the current phase. Frozen. No changes unless a specific next phase is approved. |
| `postponed` | Audit complete. Connector is not suitable or not prioritized as the next source. May be reconsidered later. Not approved for implementation now. |
| `rejected` | Evaluated and rejected permanently or for this project phase. No further work. |

---

## Source categories

| Category | What it measures |
|---|---|
| Supplier source | What products exist, their cost, availability, weight, image — what can actually be dropshipped |
| Marketplace benchmark | What buyers pay for similar products, competition level, demand evidence from real sales |
| Search demand | How many people are searching for a product or keyword; trend direction over time |
| Ad demand | Which products are actively being advertised, at what scale, by how many sellers |
| Content demand | Video/review/unboxing interest — proxy for curiosity and purchase consideration |
| Community pain / buyer intent | Real buyer complaints, questions, unmet needs expressed publicly |
| Competitor creative signal | Ad copy angles, creative formats, landing page patterns from other sellers |
| Price comparison | Retail price range validation, arbitrage margin confirmation |
| Risk / compliance signal | Brand, trademark, restricted category risk before sourcing |

---

## Source map

| Source | Category | Current status | Official API / access path | Role in product discovery | Data value | Current limitation | Implementation approved? | Next action |
|---|---|---|---|---|---|---|---|---|
| **CJ Dropshipping** | Supplier source | `closed` / frozen | CJ Open API v2.0 — `GET /v1/product/list` | Primary supplier: cost, availability, weight, image | `supplier_cost`, `image_url`, `product_weight_kg`, `item_id`, `category` | `retail_price` = None (list endpoint only); no `source_url`; Phase 2/3 enrichment not started | N/A — live and closed | Freeze. Run Phase 2 (retail enrichment) only when explicitly scheduled. |
| **eBay** | Marketplace benchmark | `closed` / frozen | eBay Browse API — production OAuth | Market price benchmark, demand/competition evidence from real listings | `retail_price`, listing count, search results by keyword | `source_url` not always returned | N/A — live and closed | Freeze. Bug fixes only if production issue confirmed. |
| **TikTok Commercial Content API** | Ad demand | `pending_access` | TikTok Commercial Content API — `POST /v2/research/adlib/ad/query/` — scope `research.adlib.basic` | Ad demand signal: which products are actively advertised, engagement data | Ad creative, engagement range, advertiser info | Support ticket submitted 2026-07-05; scope not visible in portal yet | Not yet — awaiting TikTok approval | Monitor TikTok Developer Support email. Do not touch connector. |
| **Google Trends API Alpha** | Search demand | `pending_access` | Official Google Trends API — alpha, access-gated (announced July 2025) | Search demand signal: interest over time, regional breakdown, trend direction | Interest score (0-100), daily/weekly/monthly, geo, up to dozens of terms | Alpha invitation required; docs gated; application submitted 2026-07-06 at admin@zaryotech.com | Not yet — awaiting Google invitation | Monitor alpha invitation at admin@zaryotech.com. Do not touch connector. |
| **Meta Ad Library** | Competitor creative signal | `postponed` | Meta Ad Library API — `GET /ads_archive` (Graph API v25.0) | Secondary creative-angle signal: ad copy, headlines, image snapshots | Ad creative text, page name, snapshot URL | EU restriction: non-EU ads invisible; no spend/impressions for product ads; identity confirmation required | **No** — postponed | Audit YouTube Data API first. No Meta implementation until explicitly approved. |
| **YouTube Data API** | Content demand | `official_audit` (next) | YouTube Data API v3 — official, Google API key | Content demand signal: search volume proxy, review/unboxing trends, view count | Video titles, view counts, channel info, publish dates, search result counts | API key required (free tier, daily quota); no direct purchase-intent signal | Not yet — audit not done | Run official audit next. Do not implement until audit is reviewed and approved. |
| **Reddit API** | Community pain / buyer intent | `idea` | Reddit API — official, OAuth app | Buyer pain points, unmet needs, product complaints, authentic demand signals | Post/comment content, upvotes, subreddit targeting | Rate limits on free tier; requires Reddit app registration | **No** — idea only | No action until YouTube audit is complete and owner approves Reddit audit. |
| **Amazon Product Advertising API (PA-API)** | Marketplace benchmark / price comparison | `idea` | Amazon PA-API v5 — official, requires Amazon Associates account | Market price validation, BSR, review count, category ranking | `price`, `BSR`, `review_count`, `category` | Requires Amazon Associates membership + qualifying sales; access not guaranteed | **No** — idea only | No action until explicitly scheduled for audit. |
| **Keepa API** | Marketplace benchmark / price comparison | `idea` | Keepa API — official, paid subscription | BSR history, price history, Amazon rank trends over time | Historical BSR, price min/max, rank trend | Paid subscription required; no free tier | **No** — idea only | No action until explicitly scheduled for audit. Faster to activate than PA-API if approved. |
| **Google Shopping / Merchant Center** | Price comparison | `idea` | No public product-search API for competitor data. Google Merchant Center API is for managing your own product feed. | Limited: can confirm category exists in Google Shopping; not competitor discovery | Own feed only | No official competitor-facing API exists | **No — no valid discovery path identified** | Do not schedule. Re-evaluate if an official data product is announced. |
| **Pinterest API** | Content demand / ad demand | `idea` | Pinterest API v5 — official, OAuth app | Visual trend signal: pinned products, board engagement | Pin counts, board name, image | Pinterest API v5 focuses on own content management; product search for competitor discovery is limited | **No** — idea only | Evaluate if content demand signals become a priority. No action now. |
| **AliExpress Open Platform** | Supplier source | `idea` | AliExpress Open Platform — official, requires app approval | Alternative supplier source: product catalog, price, availability | Product name, price, category, rating | App approval required from AliExpress; access review process; CJ already covers supplier source | **No** — idea only | No action while CJ is active and closed. Revisit only if supplier diversification is needed. |

---

## Decision gates

A source **cannot move to implementation** unless ALL of the following are true:

1. **Official API / access path is confirmed** — from official developer documentation only. No scraping, no unofficial clients.
2. **Access requirements are known** — account type, token type, approval process, any quota or geographic limits.
3. **Limitations are documented** — what data is NOT available, which markets or ad types are excluded, batch limits, rate limits.
4. **Data value is mapped to a product decision** — the data returned must connect to at least one of: supplier cost, market price, demand signal, risk signal, creative signal.
5. **No scraping or unofficial route is needed** — if the only path to the data is unofficial, the connector is rejected or postponed.
6. **Project owner explicitly approves implementation** — audit completion is NOT approval. A separate, explicit owner decision is required.
7. **No active connector phase is unfinished** — if a live connector has an approved next phase (e.g., CJ Phase 2), that phase takes priority over a new connector.

---

## Data-to-decision map

| Source | Data contributed | Product decision it enables |
|---|---|---|
| CJ Dropshipping | `supplier_cost`, `product_weight_kg`, `image_url`, `item_id`, `category` | Is this product sourceable? What is the floor cost? Can I make margin? |
| eBay | Market price from real listings | What is the retail ceiling? How much competition exists at that price? |
| TikTok | Ad creative, engagement range, advertiser count | Is this product actively marketed? Is ad demand accelerating? |
| Google Trends | Search interest over time, trend direction, regional breakdown | Is search demand growing, peaking, or declining? Is it seasonal? |
| YouTube | Video search result count, view counts, recency of unboxing/review content | Is there content curiosity? Are reviewers covering it? Is it emerging? |
| Reddit | Post/comment content, upvote count, subreddit targeting | Are real buyers asking about this? Are there pain points this product solves? |
| Meta Ad Library | Ad copy, headline, image snapshot (EU-reachable ads only) | What creative angles are competitors using? What messaging works? |
| Amazon / Keepa | BSR, price history, review count, category rank trend | How established is this product on Amazon? Is it growing or saturated? |

---

## Score contribution model (planned — not implemented)

Each source that contributes a confirmed signal raises the product's discovery confidence:

| Signal tier | Sources | Weight |
|---|---|---|
| Supplier confirmed | CJ Dropshipping | required — no supplier, no score |
| Market price confirmed | eBay | high — needed for margin calculation |
| Ad demand | TikTok, Meta Ad Library | high — active advertising = proven demand |
| Search demand | Google Trends | high — growth trend = momentum |
| Content demand | YouTube | medium — lagging indicator of interest |
| Community intent | Reddit | medium — authentic but noisy |
| Price validation | Amazon / Keepa | medium — confirmation, not discovery |

A product with supplier + market price + ad demand + search demand signal = high-confidence winner candidate.
A product with supplier only = unscored, cannot recommend.

---

## Recommended near-term path

### Step 1 — Complete (current)
- eBay live and closed
- CJ Dropshipping live and closed
- TikTok pending approval — do not touch
- Google Trends pending approval — do not touch
- Meta audit complete — postponed

### Step 2 — Next (audit only, no implementation)
- Run official audit of YouTube Data API v3
- Document: API key process, quota limits, what endpoints return for product keyword searches, data value, limitations
- Create `CHECKPOINT_YOUTUBE_DATA_API_AUDIT.md`
- Do NOT implement until audit is reviewed and explicitly approved

### Step 3 — Decision point (after YouTube audit)
Owner chooses one of:

**Option A — Decision Engine planning**
Start designing the scoring/recommendation engine using existing signals (eBay + CJ). No new connector needed immediately.

**Option B — CJ enrichment Phase 2 / Phase 3**
Add retail price enrichment and/or shipping cost to CJ products. Improves margin scoring without adding a new connector.

**Option C — YouTube connector implementation**
If YouTube audit confirms strong data value and is explicitly approved, implement `YoutubeConnector` as a content demand signal source.

**Options are mutually exclusive for active implementation.** Only one active connector work stream at a time.

---

## Source expansion rules

- Auditing a new source is always allowed (read-only research, no code).
- Implementing a new connector requires explicit owner approval.
- No connector is implemented in parallel with another active connector phase.
- No automatic fallback connector. If pending approvals are delayed, the project owner must explicitly approve what comes next.
- Scraping, unofficial clients, and browser automation are never allowed for any source.
