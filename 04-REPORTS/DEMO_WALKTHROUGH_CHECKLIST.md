# WPM TASK 007 — Internal Demo Walkthrough Checklist

Date: 2026-07-12

Status: Internal-only checklist

Scope: Current MVP after WPM TASK 006

This is not a paid-sales script or an external-prospect script. It does not authorize a demo launch, sales, automation, n8n, connector, or production work.

## 1. Current Confirmed State

- WPM TASK 004 completed and pushed: `f4f6644 Task WPM-004: Document n8n workflow source audit`
- WPM TASK 005 completed as a read-only Demo / Sales Readiness Review: `REVIEW PASS WITH CAUTIONS`
- WPM TASK 006 completed and pushed: `e268a09 Task WPM-006: Align product detail with Phase B decisions`
- `main` synced with `origin/main` after WPM TASK 006
- Frontend header subtitle corrected
- `GET /products/{pid}` returns Phase B decision fields
- Product detail drawer displays Phase B decision fields
- `/products` and `/export/products` include Phase B decision fields
- n8n workflows are documented as stale/gated and must not be published or activated yet

## 2. Safe Positioning Statements

- Early-stage product intelligence MVP for discovering and triaging potential winning products.
- The current system combines configured live product inputs with a deterministic Phase B decision layer.
- The MVP currently supports product review, decision filtering, missing-data visibility, detail review, and export.
- Automation and additional sources are intentionally gated until the data model and workflow semantics are aligned.
- This is an internal controlled demo, not a paid-client production system.

The demo must avoid real-time coverage claims, all-sources-active claims, automated daily workflow claims, guarantees of profitable products, and claims that TikTok, Google Trends, YouTube, Meta, Amazon/Keepa, AliExpress, or Reddit are active.

## 3. What Can Be Shown Today

- Main products table
- Decision badges
- `next_action` column
- `missing_data` column
- Decision filter
- `next_action` filter
- Missing `image_url`, `supplier_cost`, and `shipping_cost` checkboxes
- Clear/reset filters
- Product detail drawer with Phase B fields
- JSON/CSV export
- Connector health as internal operator evidence only
- eBay/CJ as configured live inputs, without overclaiming completeness
- n8n audit document as governance evidence only, not active automation

## 4. What Must Not Be Shown Yet

- n8n workflow as active or ready
- TikTok as live
- Google Trends as live
- YouTube as live
- Meta as live
- Amazon/Keepa, AliExpress, or Reddit as active sources
- Automated daily reporting
- Paid-client readiness
- External-prospect-ready claims
- Real-time pricing coverage
- Complete shipping-cost coverage
- Complete image coverage
- Any claim that current data already has TEST or WATCH products

## 5. Exact Claims To Avoid

- "No external APIs". This is inaccurate because configured live inputs may be used in the controlled MVP.
- "Sample data". This inaccurately characterizes the current configured input state.
- "The system tells you what to test right now". Current results require data-readiness context and do not guarantee an immediate TEST recommendation.
- "Automated daily reports". n8n automation is gated and not authorized for publishing, activation, or execution.
- "TikTok / Google Trends / YouTube signals included". These sources must not be represented as active.
- "Real-time pricing". The MVP does not claim real-time pricing coverage.
- "Shipping cost available". Shipping-cost fields may be incomplete.
- "Product images available". Image fields may be incomplete.

## 6. Narrative For 0 TEST And 0 WATCH Products

0 TEST and 0 WATCH products are not hidden. Current data is dominated by NEEDS_ENRICHMENT and REJECT, which shows that the decision engine is strict rather than artificially optimistic. Missing `supplier_cost`, `shipping_cost`, `image_url`, and other fields affect decision readiness.

The current value is triage, filtering, and identifying enrichment gaps. The next business question is not "why no winners?", but "which data gaps must be closed to move products from NEEDS_ENRICHMENT to TEST?"

## 7. Recommended Internal Walkthrough Order

1. Open the dashboard and explain the controlled MVP subtitle.
2. Show the products table and decision badges.
3. Explain decision meanings: REJECT, NEEDS_ENRICHMENT, WATCH, TEST.
4. Use the decision filter.
5. Use the `next_action` filter.
6. Use the missing-field filters.
7. Open the product detail drawer and show Phase B decision fields.
8. Show the export section.
9. Explain live eBay/CJ inputs carefully.
10. Explain gated sources and n8n status.
11. Close with the next internal decision: enrich data, prepare a private demo script later, build a Phase B n8n endpoint later, or fix remaining UI/demo clarity issues if discovered.

## 8. How To Explain eBay And CJ

- eBay and CJ are configured/live enough for internal MVP demonstration.
- eBay and CJ do not mean complete market coverage.
- Pricing, cost, shipping, image, and source fields may still be incomplete.
- Do not claim real-time or full supplier intelligence.
- These are current MVP inputs, not the final production source network.

## 9. How To Explain Missing Data

- Missing data is visible by design.
- `missing_data` is part of the operator workflow.
- Missing fields are enrichment gaps, not hidden failures.
- Filtering by missing `image_url`, `supplier_cost`, and `shipping_cost` helps prioritize cleanup.
- Current decision output should be read together with `missing_data` and `next_action`.

## 10. How To Explain n8n

- n8n is gated, not broken.
- The source audit found a semantic mismatch with Phase B fields.
- Existing workflow JSON files are stale and duplicate.
- Workflows must not be published or activated yet.
- This demonstrates governance discipline: automation waits until semantics are correct.
- The future safest path is likely an additive Phase B reporting endpoint, but that is not authorized by this checklist.

## 11. Internal Demo Do/Don't Checklist

Do:

- Say controlled MVP.
- Say configured live inputs.
- Say Phase B decision layer.
- Say internal demo only.
- Show missing data honestly.
- Explain enrichment gaps.
- Explain automation is gated.

Don't:

- Say production-ready.
- Say paid-client ready.
- Say automated reports are live.
- Say all sources are live.
- Say current data contains TEST/WATCH products.
- Say shipping, images, or pricing are complete.
- Say n8n is ready.
- Say TikTok, Trends, YouTube, or Meta are included.

## 12. Final Internal Recommendation

- Internal walkthrough can proceed after this checklist.
- External demo should wait for a separate private-prospect script.
- Paid sales should wait for stronger data readiness and clearer TEST/WATCH examples.
- No technical implementation is authorized by this document.
