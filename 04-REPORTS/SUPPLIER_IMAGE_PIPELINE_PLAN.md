# WPM TASK 010B — Supplier Image Pipeline Plan

## Purpose And Background

This document records the proposed future supplier image pipeline for WINNING-PRODUCTS-MVP. It is based on the WPM TASK 010A OpenCode read-only audit and Claude Code QA review.

The objective is to replace reliance on manually approved `image_url` values with a controlled, traceable supplier-image process. The first permitted supplier source for a future implementation is CJ Dropshipping. A future hosted asset URL, after approval and validation, should become the canonical product display image.

This document is planning only. It does not authorize schema changes, database writes, connector calls, image downloads, image hosting, provider setup, or application changes.

## Current Findings From WPM TASK 010A

- CJ live discovery maps `productImage` to `image_url` in the CJ product-list mapper.
- CJ stub products do not include `image_url`; stub data cannot validate a supplier-image flow.
- New eBay discoveries currently capture `image_url`.
- Existing older eBay rows may lack `image_url` because of the historical discovery backlog.
- The database currently has `products.image_url TEXT`.
- The schema has no image provenance, hosted URL, license or usage assumption, approval status, ingestion status, or image-specific timestamp fields.
- `ProductIn` excludes `image_url`.
- `db.ALLCOLS` excludes `image_url`.
- `insert_product()` silently drops an `image_url` supplied through that generic path.
- `upsert_discovered_candidate()` preserves `image_url` for discovered candidates.
- The decision engine treats any non-`None` `image_url` as present.
- An empty string or broken URL can therefore create a false image-readiness signal unless future validation prevents it.
- The frontend does not render product images. It currently only filters discovered products by missing `image_url`.

## Future Pipeline Design

### Source Policy

- CJ Dropshipping must be the first and only supplier-image source in the initial future implementation.
- eBay image behavior may remain documented as discovery metadata, but eBay must not be used as a supplier-image pipeline source at this stage.
- Manual image URLs, random public image URLs, marketplace seller images, and eBay seller images are forbidden for this pipeline.
- A raw CJ supplier URL is evidence of an available supplier image, not proof that the asset is production-ready, licensed, approved, valid, or hosted.

### Canonical URL Policy

- Supplier provenance must be retained for every accepted image.
- `original_supplier_image_url` must retain the CJ-origin URL received from the supplier source.
- `hosted_image_url` should become the future canonical display URL only after approval, controlled ingestion, hosting, and verification.
- Raw supplier URLs must not be rendered as production product images or treated as production-ready image proof.

### Proposed Flow

1. Capture a CJ `productImage` with CJ source identity and CJ product ID.
2. Record the image as `discovered` without treating it as display-ready.
3. Require rights or usage review.
4. Validate the source URL and image response under the safeguards in this document.
5. Approve eligible assets for controlled ingestion.
6. Ingest to the approved hosted-image provider.
7. Store the hosted URL and verification metadata.
8. Permit frontend display and decision readiness only for an approved, hosted, verified image.

## Proposed Future Fields

| Field | Intended purpose |
|---|---|
| `original_supplier_image_url` | Original image URL returned by CJ. |
| `hosted_image_url` | Controlled hosted asset URL; future canonical display URL. |
| `image_source_name` | Supplier source identifier, initially `cj_dropshipping`. |
| `image_source_product_id` | Supplier product identifier, initially the CJ `pid`. |
| `image_ingestion_status` | Current lifecycle state for intake, validation, and hosting. |
| `image_license_assumption` | Recorded policy basis or supplier-terms assumption; not legal proof. |
| `image_approval_status` | Explicit approval outcome for use and ingestion. |
| `image_approval_note` | Operator or policy note supporting the approval outcome. |
| `image_content_hash` | Hash for deduplication and content-change detection. |
| `image_mime_type` | Verified image media type. |
| `image_width` | Verified pixel width. |
| `image_height` | Verified pixel height. |
| `image_ingested_at` | Timestamp of controlled ingestion attempt or completion. |
| `image_approved_at` | Timestamp of explicit approval. |
| `image_hosted_at` | Timestamp when the hosted asset became available. |
| `image_last_verified_at` | Timestamp of the most recent successful validation. |
| `image_failure_reason` | Machine-readable or operator-readable reason for rejection or failure. |

The schema design gate must define exact types, nullability, indexes, enum constraints, ownership, retention, and whether current `image_url` remains transitional or is retired.

## Lifecycle Statuses

The future `image_ingestion_status` lifecycle should use only these states unless a separately approved schema design changes them:

| Status | Meaning |
|---|---|
| `discovered` | Supplier image URL was captured, but has not been reviewed or validated. |
| `rights_review_required` | Usage or supplier-rights review is required before ingestion. |
| `approved_for_ingestion` | Approved for controlled download and hosting, subject to technical validation. |
| `hosted` | Asset was ingested and a hosted URL was recorded; verification may still be pending. |
| `verified` | Hosted asset and required metadata were successfully validated. |
| `rejected` | Not approved for use or ingestion. |
| `failed` | Validation, retrieval, ingestion, or hosting failed. |
| `expired` | Source or hosted asset is no longer valid or available. |

No raw supplier URL should move a product directly to `verified`.

## Validation Safeguards

- Accept HTTPS URLs only.
- Require a non-empty URL.
- Reject blank and whitespace-only strings.
- Check the image response before treating an image as ready.
- Validate the response MIME type against the permitted image types.
- Enforce a configured download and decoded-image size limit.
- Compute and retain a content hash for deduplication and content-change detection.
- Record a failure reason for every rejected, failed, or expired image.
- Record `image_last_verified_at` after successful validation.
- Prevent redirects to unsafe schemes or private/internal network destinations.
- Apply reasonable timeout, retry, and rate-limit controls in any future ingestion implementation.
- Never allow an invalid, broken, unverified, or merely non-empty `image_url` to satisfy TEST readiness.

## Future Decision Engine Semantics

Future decision logic must distinguish image discovery from image readiness.

- Image readiness should require an approved hosted image, not only `image_url is not None`.
- A raw supplier `image_url` must not clear `missing_data` by itself.
- Empty strings and broken URLs must be treated as missing or invalid.
- `discovered`, `rights_review_required`, `approved_for_ingestion`, `failed`, `rejected`, and `expired` must not satisfy image readiness.
- Only a valid `hosted_image_url` with the required approval and verified status should satisfy the future image prerequisite for TEST.
- Any decision-engine change requires its own gate and dedicated tests for valid, empty, broken, unapproved, failed, hosted, and verified image states.

## Future Frontend Behavior

- Do not render unapproved original supplier URLs.
- Render only the approved hosted image URL.
- Show image status, source, approval state, and failure reason in product detail.
- Add future filters for missing, failed, pending, and approved image status.
- Preserve clear distinction between supplier-source metadata and the approved hosted display image.
- Provide a safe fallback state when no verified hosted image exists; do not silently substitute a marketplace, manual, or random public image.

Frontend rendering requires a separate implementation gate and must not begin from this document alone.

## Cloudinary MVP Decision Record

Cloudinary is conditionally recommended as the MVP hosted-image storage option after the required policy, schema, and provider gates are approved. Its managed asset storage, delivery CDN, transformations, and asset metadata make it suitable for a small controlled MVP.

- No Cloudinary setup is authorized by this task.
- Shopify Files is deferred until the e-commerce storefront flow is confirmed.
- S3 or R2 is deferred as a later infrastructure option when greater storage ownership, custom delivery, and operational control justify the implementation effort.
- Provider selection does not remove the need for supplier provenance, approval, validation, retention, deletion, audit, and access-control rules.

## Write Path Risks

- `ProductIn` and `insert_product()` cannot currently persist `image_url` through the generic manual insertion path.
- A future gated implementation would require either a named, validated helper function or a specifically designed database write path. Direct SQL `UPDATE` must not be introduced without the relevant gate.
- `upsert_discovered_candidate()` currently persists discovered `image_url` values, but its deduplication and insert-only behavior must be reviewed before implementing image metadata updates, approvals, re-hosting, or backfills.
- Future writes must preserve source identity and product identity, avoid overwriting approved hosted assets with raw supplier values, and retain audit timestamps and failure information.
- No write path may be used to modify product IDs 1 or 20 without explicit separate approval.

## Non-Goals

This task does not authorize or perform any of the following:

- Database changes or migrations.
- Cloudinary setup.
- Shopify Files, S3, or R2 setup.
- Image downloading, validation requests, transformation, or hosting.
- Backend, frontend, connector, decision-engine, n8n, automation, or product-action-queue implementation.
- Database writes, backfills, seed/import/sync scripts, or enrichment writes.
- Changes to product IDs 1 or 20.
- Any eBay, marketplace seller image, manual image URL, or random public image proof of concept.

## Explicit Future Implementation Gates

Implementation may proceed only through separate, explicitly approved gates in this order where applicable:

1. Schema design gate: define and approve the exact data model, lifecycle constraints, transition rules, retention, and migration plan.
2. Storage provider setup gate: approve the provider, account boundaries, credentials, access controls, upload policy, transformations, and deletion process.
3. Image ingestion implementation gate: implement CJ-only controlled retrieval, validation, hashing, approval checks, hosting, and failure handling.
4. Decision engine gate: replace raw URL presence checks with approved hosted-image readiness semantics and comprehensive tests.
5. Frontend rendering gate: render only approved hosted images and add status, provenance, failure information, and filters.
6. Database write or backfill gate: approve any migration, update, correction, or backfill scope separately, including explicit protection for IDs 1 and 20.

No gate is implied by this document. Each gate requires its own scope, implementation review, verification plan, and explicit approval before work begins.
