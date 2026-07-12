# WPM TASK 004 — n8n Workflow Source Audit Findings

Date: 2026-07-12

Status: Documentation checkpoint after WPM TASK 003 read-only audit.

This document records the read-only findings from WPM TASK 003.

WPM TASK 003 did not modify files, did not create files, did not publish workflows, did not activate workflows, did not execute workflows, did not call n8n runtime APIs, did not access credentials, did not access environment variables, did not commit, and did not push.

## 1. Audited Files

The WPM TASK 003 audit inspected these existing files:

- `n8n-workflows/DELIVERY_WORKFLOW_GUIDE.md`
- `n8n-workflows/auto-discovery-daily-report-phase-2c-a.json`
- `n8n-workflows/auto-discovery-daily-report-phase-2c-b-ebay-sandbox.json`
- `n8n-workflows/auto-discovery-daily-report-phase-2c-c-scoring-report.json`

No runtime n8n instance was called.

No workflow was published, activated, or executed.

## 2. Critical Finding — Duplicate Workflow Exports

The three JSON workflow exports are byte-for-byte duplicates.

The duplicate files are:

- `n8n-workflows/auto-discovery-daily-report-phase-2c-a.json`
- `n8n-workflows/auto-discovery-daily-report-phase-2c-b-ebay-sandbox.json`
- `n8n-workflows/auto-discovery-daily-report-phase-2c-c-scoring-report.json`

They have the same:

- workflow name
- workflow id
- versionId
- node structure
- code
- endpoints

Only one unique workflow exists in the source exports.

The Phase 2C-A / Phase 2C-B / Phase 2C-C distinction implied by the filenames is not reflected in the actual file contents.

This must be resolved before any future publish, activation, or automation work.

## 3. Existing Workflow Structure

The existing workflow source is manual and inactive in the exported source.

Observed workflow characteristics:

- trigger type: `manualTrigger`
- active status in source: `active: false`
- no schedule trigger confirmed in the JSON exports
- no approved publish state
- no approved activation state

Observed workflow chain:

1. Manual trigger
2. `POST /sources/ebay/discover`
3. Code node extracts candidates
4. `POST /discovery/manual`
5. Code node collects inserted IDs
6. `GET /reports/daily`
7. Code node builds an Arabic summary from report fields

The workflow can run mechanically against existing backend endpoints, but its reporting logic is semantically stale compared with the Phase B frontend decision fields.

## 4. Old Field Usage

The existing workflow currently uses old scoring/reporting fields.

Old fields and labels observed in the workflow/reporting logic include:

- `by_recommendation`
- `recommendation`
- `score`
- `average_score`
- `Reject`
- `Watchlist`
- `Test with small budget`
- `Strong candidate`

These fields belong to the older scoring/report shape.

They do not represent the current Phase B decision engine output shown in the frontend.

## 5. Phase B Fields Not Used

The existing workflow does not use the current Phase B decision engine fields.

Missing Phase B field usage:

- `decision`
- `next_action`
- `missing_data`
- `decision_confidence`
- `margin_status`
- `estimated_net_margin`
- `risk_flags`
- `decision_reasons`

This creates a semantic mismatch between the n8n report output and the current frontend decision workflow.

## 6. Backend Report Endpoint Finding

The audit confirmed that `/reports/daily` still uses the older scoring path.

Important finding:

- `/reports/daily` uses `scoring.score_product`
- `/reports/daily` does not call `decision_engine.decide_product`
- `/reports/daily` returns old recommendation/score style report fields
- the `decision` field inside `/reports/daily` is legacy `action_plan` decision
- the `decision` field inside `/reports/daily` is not the Phase B decision engine output

Therefore, a workflow that calls `/reports/daily` will not receive the same Phase B decision information that the frontend currently displays.

## 7. Semantic Compatibility Assessment

Existing n8n workflow source is pre-Phase-B.

Current frontend status is Phase B.

Frontend now displays or filters with fields such as:

- `decision`
- `next_action`
- `missing_data`

The existing n8n workflow still reports old values such as:

- `recommendation`
- `score`
- `by_recommendation`

Result:

- the workflow can likely run mechanically
- the workflow output would be semantically stale
- the workflow output would not match the current frontend decision workflow
- publishing the existing JSONs would create confusing reports

## 8. Blockers Before Future Publish

The existing workflow JSONs must not be published or activated until these blockers are resolved.

Blockers:

1. Old field usage
   - workflow logic still uses old recommendation/score fields

2. Duplicate workflow exports
   - three JSON files are identical despite different filenames

3. `/reports/daily` is not Phase B aligned
   - it uses old scoring logic and does not call `decision_engine.decide_product`

4. Manual trigger only
   - the workflow source uses `manualTrigger`, not an approved schedule trigger

5. Publish / activation not approved
   - no publish Gate has been approved
   - no activation Gate has been approved

## 9. Delivery Workflow Guide Note

`n8n-workflows/DELIVERY_WORKFLOW_GUIDE.md` describes a future delivery workflow direction.

It does not prove that the current JSON workflow exports implement that future delivery path.

The existing JSON workflow exports call:

- `GET /reports/daily`

They do not implement a confirmed Phase B n8n delivery workflow.

Any future delivery workflow work requires separate owner approval and a new Gate 1.

## 10. Recommended Future Technical Direction

The safest future technical path appears to be an additive Phase B reporting endpoint for n8n.

Recommended future direction for discussion:

- create a new backend endpoint specifically for n8n Phase B reporting
- leave `/reports/daily` unchanged initially
- avoid breaking any existing consumer of `/reports/daily`
- make the n8n workflow consume a Phase B-specific report shape later

This document does not authorize that implementation.

Any future endpoint, backend change, or n8n workflow edit requires a separate Gate 1.

## 11. Current Recommendation

Do not publish the existing workflow JSON exports.

Do not activate the existing workflow JSON exports.

Do not execute the existing workflow as production automation.

Do not edit the workflow JSON files under this task.

Recommended next step after this documentation checkpoint:

- discuss a separate future technical task for a Phase B n8n reporting path
- likely safest path: additive Phase B reporting endpoint for n8n
- any technical fix requires separate Gate 1 approval

## 12. Non-Authorization Statement

This document does not authorize:

- backend implementation
- frontend implementation
- n8n workflow edit
- n8n workflow publish
- n8n workflow activation
- n8n workflow execution
- n8n runtime API calls
- credentials access
- environment variable access
- database work
- connector work
- automation
- product action queue implementation
- demo launch
- sales launch
- deployment
- external API connection
- production access
- Git commit without Gate 2
- Git push without Push Gate

End of WPM TASK 004 n8n workflow source audit documentation.
