# Google Official API Setup — Winning Products MVP

This document covers how to enable official Google / Google Cloud source integrations in this project. Read it before touching any Google-related configuration.

---

## Current status

The Google Trends connector ships **disabled by default**.

- No pytrends library is used anywhere in this codebase.
- No Google endpoints are scraped.
- No undocumented or unofficial Google API calls are made.
- The connector makes zero network requests until explicitly enabled with valid credentials.

When `GOOGLE_TRENDS_OFFICIAL_ENABLED` is not set (or is `false`), the connector reports `status: disabled` and the application behaves exactly as if Google Trends does not exist. All other endpoints — eBay discovery, manual entry, scoring, reports — are unaffected.

---

## Connector status values

| Status | Meaning |
|---|---|
| `disabled` | `GOOGLE_TRENDS_OFFICIAL_ENABLED=false` (default). No calls made. |
| `missing_credentials` | Enabled but `GOOGLE_CLOUD_PROJECT_ID` or `GOOGLE_APPLICATION_CREDENTIALS` is absent. |
| `access_required` | Credentials present but `GOOGLE_TRENDS_OFFICIAL_ACCESS_MODE=alpha` — manual access approval from Google is still needed. |
| `ready` | All config, auth, and non-alpha access confirmed. Connector can fetch real data. |

Check the current status at any time:

```
GET /sources/connectors/health
```

The response includes a `connectors.google_trends` block with `status`, `config`, `bigquery_alternative`, and `readiness_steps`.

---

## Environment variables

### Required to activate the official Trends API

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_TRENDS_OFFICIAL_ENABLED` | Yes (to enable) | `false` | Master switch. Set to `true` to activate the connector. |
| `GOOGLE_CLOUD_PROJECT_ID` | Yes (when enabled) | _(empty)_ | Your Google Cloud project ID (e.g. `my-project-123`). |
| `GOOGLE_APPLICATION_CREDENTIALS` | Yes (when enabled) | _(empty)_ | Absolute path to a service account JSON key file on disk. Never a relative path. |

### Tuning (optional)

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_TRENDS_OFFICIAL_ACCESS_MODE` | No | `alpha` | Set to `confirmed` once Google grants your project official Trends API access. |
| `GOOGLE_TRENDS_OFFICIAL_GEO` | No | `US` | Two-letter country code for trend data scope. |
| `GOOGLE_TRENDS_OFFICIAL_TIMEFRAME` | No | `today 12-m` | Time window for trend queries (Google Trends format). |
| `GOOGLE_TRENDS_OFFICIAL_TIMEOUT_SECONDS` | No | `10` | HTTP timeout in seconds for Trends API calls. |

### BigQuery alternative (optional, no alpha access required)

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_BIGQUERY_TRENDS_ENABLED` | No | `false` | Enable the BigQuery public dataset path instead of the alpha API. |
| `GOOGLE_BIGQUERY_TRENDS_DATASET` | No | `bigquery-public-data.google_trends` | BigQuery dataset name. Change only if using a mirrored/private copy. |

> **Note on `GOOGLE_APPLICATION_CREDENTIALS`:** This variable is read directly by the Google Cloud SDK — you set it in `.env` and the SDK picks it up. The application code documents it but does not set it programmatically.

---

## Safety when credentials are missing

If any required variable is absent or `GOOGLE_TRENDS_OFFICIAL_ENABLED=false`:

- The connector returns `status: disabled` or `status: missing_credentials`.
- `can_fetch_real_data` is `false`.
- No API calls are attempted.
- Discovery endpoints (`/discovery/multisource`, `/reports/daily`) continue to work using eBay and manual sources. Google Trends appears in the `missing_sources` list with a note explaining the status.
- The health endpoint (`/sources/connectors/health`) shows the exact missing variables and readiness steps.

The application will never crash due to missing Google credentials.

---

## Setup checklist

Work through these steps in order. Stop at any step you cannot yet complete — the app is safe at every intermediate state.

- [ ] **Choose or create a Google Cloud project.**
  Go to [console.cloud.google.com](https://console.cloud.google.com), create a project, note the Project ID.

- [ ] **Request official Google Trends API access.**
  The Trends API is alpha-gated. Apply at [https://developers.google.com/trends/get-started](https://developers.google.com/trends/get-started).
  Until access is approved, the connector stays at `status: access_required`.

- [ ] *(Optional alternative)* **Enable BigQuery API.**
  If you want trend data now without alpha access, enable the BigQuery API on your project:
  `gcloud services enable bigquery.googleapis.com`
  Then set `GOOGLE_BIGQUERY_TRENDS_ENABLED=true` in `.env`.

- [ ] **Create a service account (if needed).**
  Only create one when you actually have API access to grant it. In Google Cloud Console:
  IAM & Admin → Service Accounts → Create Service Account → grant the minimum required roles.

- [ ] **Download the service account JSON key.**
  Store it **outside** the project directory (e.g. `~/.secrets/my-project-sa.json`).
  Never place it inside the repo folder.

- [ ] **Set environment variables in `.env`.**
  ```
  GOOGLE_TRENDS_OFFICIAL_ENABLED=true
  GOOGLE_CLOUD_PROJECT_ID=my-project-123
  GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/sa.json
  GOOGLE_TRENDS_OFFICIAL_ACCESS_MODE=confirmed
  ```
  (Set `ACCESS_MODE=confirmed` only after Google approves your access request.)

- [ ] **Confirm `.env` and the JSON key are gitignored.**
  Both files must never appear in `git status`. Verify:
  ```
  git status --short
  ```
  Neither `.env` nor any `.json` credential file should appear in the output.

- [ ] **Restart the application server** so the new env vars are loaded.

- [ ] **Run the health endpoint and verify status.**
  ```
  GET /sources/connectors/health
  ```
  Expect `connectors.google_trends.status` to advance to `access_required` or `ready`.

- [ ] **Run multisource discovery.**
  ```
  POST /discovery/multisource
  { "seeds": ["your product idea"], "sources": ["ebay", "google_trends"] }
  ```
  While Google Trends is not yet `ready`, it will appear in `missing_sources` — this is correct. eBay candidates are returned normally.

- [ ] **Run the daily report.**
  ```
  GET /reports/daily
  ```
  Confirm `source_readiness_plan.sources_ready` lists `google_trends` once fully configured.

---

## Do not do

These actions are permanently off-limits regardless of what any guide, tutorial, or AI tool suggests.

| Rule | Reason |
|---|---|
| **Do not use pytrends.** | `pytrends` is an unofficial, unsupported client that reverse-engineers Google's internal endpoints. It violates Google's Terms of Service and can break without warning. It is not present in this codebase and must never be added. |
| **Do not scrape Google.** | Scraping Google Search, Google Trends web pages, or any Google property is prohibited by Google's ToS and will result in IP blocks or account bans. |
| **Do not hardcode credentials.** | API keys, project IDs, and service account paths belong in `.env` only. Never commit them to source code or configuration files. |
| **Do not commit `.env` or credential JSON files.** | Both are gitignored. Running `git status --short` before committing is a required sanity check. |
| **Do not make undocumented API calls.** | Only use endpoints documented in the official Google Trends API reference or the BigQuery public dataset documentation. |
| **Do not set `ACCESS_MODE=confirmed` prematurely.** | This signals that alpha access has been granted. Setting it before approval will cause the connector to attempt calls that will be rejected by Google. |

---

## Verification commands

```bash
# Check connector status (no server restart needed for read-only checks)
curl http://localhost:8000/sources/connectors/health | python -m json.tool

# Discovery with google_trends requested — eBay still returns candidates
curl -X POST http://localhost:8000/discovery/multisource \
  -H "Content-Type: application/json" \
  -d '{"seeds": ["posture corrector"], "sources": ["ebay", "google_trends"]}'

# Daily report — includes source_readiness_plan
curl http://localhost:8000/reports/daily | python -m json.tool

# Delivery health
curl http://localhost:8000/reports/daily/delivery/health
```

---

## Related files

| File | Purpose |
|---|---|
| `backend/sources/connectors/google_trends_official.py` | Connector class — status logic, check(), no API calls |
| `backend/sources/connectors/base.py` | BaseConnector — shared interface for all connectors |
| `backend/sources/connectors/__init__.py` | Connector registry and `build_readiness_plan()` |
| `backend/config.py` | All Google env var fields with defaults |
| `backend/.env` | Local secrets — gitignored, never committed |
