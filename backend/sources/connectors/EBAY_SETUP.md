# eBay Connector Setup & Safety Reference

Covers `backend/sources/connectors/ebay_official.py` (the gated wrapper) and
`backend/sources/ebay.py` (the underlying OAuth client-credentials / Browse
API implementation). Official eBay Browse API only — no scraping, no
unofficial endpoints.

## Current status (as of Phase 3D)

- **Sandbox: ready.** Live OAuth + Browse API calls succeed in sandbox when
  enabled (verified in Phase 3B/3C/3D smoke tests).
- **Production: intentionally blocked.** No production call is ever made by
  this codebase, regardless of which environment variables are set. Enabling
  real production traffic is a deliberate, separate, later phase — not a
  configuration toggle.

## Required environment variables

All of these live in `backend/.env` (never committed — see Safety rules).
`backend/.env.example` documents the same names with placeholder/blank values.

| Variable | Purpose | Default |
|---|---|---|
| `EBAY_CLIENT_ID` | Sandbox/app client ID | (none) |
| `EBAY_CLIENT_SECRET` | Sandbox/app client secret | (none) |
| `EBAY_ENVIRONMENT` | `sandbox` or `production` | `sandbox` |
| `EBAY_MARKETPLACE_ID` | eBay marketplace, e.g. `EBAY_US` | `EBAY_US` |
| `EBAY_LIVE_ENABLED` | Master gate — no eBay request is made unless `true` | `false` |
| `EBAY_PRODUCTION_CLIENT_ID` | Production client ID (readiness tracking only) | (none) |
| `EBAY_PRODUCTION_CLIENT_SECRET` | Production client secret (readiness tracking only) | (none) |
| `EBAY_PRODUCTION_READY` | Explicit operator confirmation that production access was approved | `false` |

## Connector status values

Returned by `EbayOfficialConnector.status` and surfaced at
`GET /sources/connectors/health`:

- `disabled` — `EBAY_LIVE_ENABLED` is not `true`. No request is sent.
- `missing_credentials` — live mode is enabled but the credentials for the
  active environment (sandbox or production) are not set.
- `access_required` — production environment selected; production
  credentials and/or `EBAY_PRODUCTION_READY` confirmation are incomplete, or
  even complete (production rollout is still code-blocked — see below).
- `ready` — sandbox, live enabled, sandbox credentials present. The only
  status under which real eBay requests are made.

`check()` also returns a `production_readiness` object with:
`production_client_id_set`, `production_client_secret_set`,
`production_ready_confirmed`, `production_readiness_status`,
`production_calls_allowed` (always `false` in the current build),
`next_manual_steps`.

## Safety rules

- Never commit `backend/.env`. It is listed in `.gitignore` and must stay
  untracked. Only `backend/.env.example` (placeholders, no real values) is
  committed.
- Never print `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`,
  `EBAY_PRODUCTION_CLIENT_ID`, `EBAY_PRODUCTION_CLIENT_SECRET`, or any OAuth
  token. Code and tooling should only check presence (`bool(...)`), never log
  the value.
- `search_items()` hard-refuses any call while `EBAY_ENVIRONMENT=production`,
  independent of the `status` gate — this is a defense-in-depth check so that
  no combination of environment variables can trigger a real production
  request from this build.
- Sandbox failures fall back to clearly labeled stub data
  (`ebay_stub` / `ebay_stub_fallback`) in `/discovery/multisource` — never
  silently fabricated as real.

## Exact steps for future production activation (not done yet)

This build deliberately stops short of enabling production traffic. A future
phase would need to, in order:

1. Obtain an approved eBay production keyset (production traffic requires
   eBay's approval beyond what sandbox needs).
2. Set `EBAY_PRODUCTION_CLIENT_ID` and `EBAY_PRODUCTION_CLIENT_SECRET` in
   `backend/.env` (manually — never via committed code or this assistant).
3. Set `EBAY_PRODUCTION_READY=true` in `backend/.env` once access is
   confirmed with eBay.
4. Set `EBAY_ENVIRONMENT=production` in `backend/.env`.
5. **Code change required:** remove or relax the hard production refusal in
   `EbayOfficialConnector.search_items()` (currently unconditional) and adjust
   `production_readiness()`'s `production_calls_allowed` to reflect the real
   gate state. This is an explicit, reviewed code change — not something that
   happens automatically from setting environment variables alone.
6. Re-run the full eBay acceptance test suite against production before
   relying on it.

Until step 5 happens, production stays blocked no matter what is set in
`.env`.
