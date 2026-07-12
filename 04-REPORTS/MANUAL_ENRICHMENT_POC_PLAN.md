# WPM TASK 009C — Manual Enrichment POC Plan

Date: 2026-07-12

Status: Documentation-only plan

Scope: Plan only, no DB writes.

Source audit: WPM TASK 009B Manual Enrichment POC Candidate Audit.

This document does not authorize implementation or database updates. Any actual `image_url` update requires separate WPM TASK 010 Gate 1 approval.

## 1. Purpose

The goal is to create the first controlled manual enrichment proof-of-concept (POC). The POC is designed to validate that adding the missing `image_url` to selected manually entered products can move them from NEEDS_ENRICHMENT to TEST.

This is not a live automatic discovery result. It is not a paid-sales or external-prospect demo artifact.

## 2. Selected POC Batch

### Product 1: Smart Posture Trainer (premium)

- ID: 20
- Current decision: NEEDS_ENRICHMENT
- Current `missing_data`: `image_url`
- Simulated decision after `image_url`: TEST
- Simulated `next_action`: `prepare_test_offer`
- Simulated `decision_confidence`: HIGH
- Simulated `margin_status`: `strong_margin`
- Simulated `estimated_net_margin`: 23.0
- Reason selected: strongest candidate, High confidence 19/19, Test with small budget, positive margin, no risk flags

### Product 2: Posture Corrector Back Brace

- ID: 1
- Current decision: NEEDS_ENRICHMENT
- Current `missing_data`: `image_url`
- Simulated decision after `image_url`: TEST
- Simulated `next_action`: `prepare_test_offer`
- Simulated `decision_confidence`: HIGH
- Simulated `margin_status`: `acceptable_margin`
- Simulated `estimated_net_margin`: 10.0
- Reason selected: clean TEST candidate, High confidence 19/19, Test with small budget, positive margin, no risk flags

## 3. Why Only These Two Products

They are the only two audited candidates that cleanly reach TEST after hypothetical `image_url` completion. Both pass all TEST conditions:

- Not eliminated
- Confidence High
- Recommendation Test with small budget
- No `caution_reasons`
- `positive_reasons` present
- `net_profit` > 0
- `missing_data` empty after `image_url` completion

Other audited products are excluded:

- ID 5 Portable Mini Blender: WATCH only, not TEST
- ID 16 Cervical Neck Traction Device: WATCH only, not TEST
- ID 4 Argan Oil Hair Serum: WATCH with regulatory/caution risk and zero margin
- ID 22 Travel Compression Packing Cubes: WATCH but weak, Low confidence, score recommendation Reject, zero margin

## 4. Current And Simulated Decision Evidence

| ID | Product | Current decision | Current missing_data | Current score/recommendation | Current confidence | Current estimated margin | Simulated decision after image_url | Simulated next_action | Simulated reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 20 | Smart Posture Trainer (premium) | NEEDS_ENRICHMENT | image_url | 47.0/60; Test with small budget | High 19/19 | 23.0 | TEST | prepare_test_offer | Image completion removes the only decision-readiness gap; positive margin and no risk flags remain. |
| 1 | Posture Corrector Back Brace | NEEDS_ENRICHMENT | image_url | 45.5/60; Test with small budget | High 19/19 | 10.0 | TEST | prepare_test_offer | Image completion removes the only decision-readiness gap; positive margin and no risk flags remain. |

## 5. Image URL Input Requirements

- Must be a valid HTTPS URL.
- Must point to a product-relevant image.
- Must not be a random placeholder in the actual DB write task.
- Must not be misleading, fake, unrelated, or copyrighted in a way that creates commercial risk.
- Must be manually reviewed before any DB write.
- Must be stored only after WPM TASK 010 Gate 1 approval.
- For planning, no specific live image URL is approved yet.

## 6. Honest Labeling Requirement

"Manually entered product with manually researched pricing and signal data — included as an internal proof-of-concept to validate decision engine output. This is not a live discovery result, not an automated output, and not a production-ready signal."

This label must be used whenever the POC products are shown internally. They must not be represented as:

- Live automatic discovery output
- Fully automated result
- Production-ready winner
- Paid-client-ready signal
- Representative of eBay or CJ connector performance

## 7. Success Criteria

- After a WPM TASK 010 controlled DB write, ID 20 and ID 1 should show decision TEST.
- Both should show `next_action` `prepare_test_offer`.
- Both should show empty `missing_data`.
- Both should show `decision_confidence` HIGH.
- Detail drawer should show Phase B decision fields correctly.
- Decision filter TEST should show at least these two products.
- Honest manual POC labeling must be used in any explanation.

## 8. Failure Criteria

- Either ID 20 or ID 1 remains NEEDS_ENRICHMENT after an `image_url` update.
- Either product becomes WATCH or REJECT unexpectedly.
- `missing_data` still includes `image_url` after update.
- `next_action` is not `prepare_test_offer`.
- Detail drawer fails to show Phase B fields.
- Products are presented as live automatic discovery results.
- Any unapproved DB write or file/code change happens.

## 9. Demo Safety Rules

- Internal POC only.
- Not external-prospect ready.
- Not paid-client ready.
- Do not claim the products are automatically discovered winners.
- Do not claim the system has paid-sales readiness.
- Do not show these products without the honest labeling requirement.
- Do not use this POC to imply eBay/CJ can currently generate TEST products automatically.

## 10. Forbidden Actions

- No database writes under this task.
- No `image_url` update under this task.
- No backend implementation.
- No frontend implementation.
- No connector work.
- No n8n work.
- No discovery.
- No external APIs.
- No production services.
- No automation.
- No sales launch.
- No demo launch.
- No commit without Gate 2.
- No push without Push Gate.

## 11. WPM TASK 010 Preparation

- WPM TASK 010 may later be a controlled DB-write execution task.
- It should update only `image_url` for ID 20 and ID 1.
- It must require exact approved image URLs before execution.
- It must use a separate Gate 1.
- It must verify before/after decisions.
- It must not modify code.
- It must not run discovery.
- It must not touch any product except ID 20 and ID 1.

## 12. Non-Authorization Statement

This document does not authorize backend work, frontend work, database writes, image_url updates, connector work, n8n work, automation, discovery, external API calls, production access, demo launch, sales launch, commit, or push. Any actual enrichment execution requires a separate WPM TASK 010 Gate 1.
