# n8n Delivery Workflow Guide — Phase 2F-D

## Overview

The backend exposes a delivery-ready endpoint that n8n can call to send the daily
product report via email, Google Sheets, Notion, or any other channel.

**No external credentials are configured in the backend yet.**
All delivery is performed by n8n using its own credential nodes.

---

## Delivery Endpoint

```
GET http://127.0.0.1:8000/reports/daily/delivery
```

Returns a `payload_version: "2F-D"` object with all fields needed for delivery.

### Preflight Health Check

Before running delivery nodes, call the health endpoint:

```
GET http://127.0.0.1:8000/reports/daily/delivery/health
```

Returns `ok: true/false` and `delivery_status: "ready" | "needs_review"`.

If `ok` is `false` or `delivery_status` is `"needs_review"`, skip delivery and
alert the operator instead.

---

## How to Use the Payload in n8n

### Email (Gmail / SMTP node)

| n8n field      | Source in payload            |
|----------------|------------------------------|
| Subject        | `n8n_payload.subject`        |
| Plain text     | `n8n_payload.text`           |
| HTML body      | `n8n_payload.html`           |

Credentials: configure Gmail OAuth or SMTP credentials in n8n.
The backend does NOT hold any email credentials.

### Google Sheets (Google Sheets node)

| n8n field      | Source in payload            |
|----------------|------------------------------|
| Rows to append | `n8n_payload.rows`           |

Each row in `n8n_payload.rows` contains the following columns:

```
generated_at_utc, source, product_name, score, recommendation,
decision, decision_reason, quality_status,
retail_price, shipping_cost, estimated_margin,
demand_signal, trend_signal, competition_signal,
supplier_signal, margin_signal,
positive_reasons, caution_reasons, filter_reasons, missing_data
```

Credentials: configure Google Sheets OAuth2 credentials in n8n.
The backend does NOT hold any Google credentials.

### Notion (Notion node)

| n8n field           | Source in payload                    |
|---------------------|--------------------------------------|
| Page title          | `n8n_payload.subject`                |
| Body content        | `n8n_payload.text` or `n8n_payload.html` |
| Decision property   | `n8n_payload.decision`               |
| Quality status      | `n8n_payload.quality_status`         |
| Top candidates      | `n8n_payload.rows` (as database rows)|

Credentials: configure Notion Internal Integration Token in n8n.
The backend does NOT hold any Notion credentials.

---

## Payload Fields Reference

| Field                  | Type     | Description                                      |
|------------------------|----------|--------------------------------------------------|
| `payload_version`      | string   | Schema version — current: `"2F-D"`               |
| `generated_at_utc`     | string   | ISO timestamp when the report was generated      |
| `delivery_status`      | string   | `"ready"` or `"needs_review"`                    |
| `delivery_channels`    | array    | `["email", "google_sheets", "notion", "n8n"]`    |
| `top_candidates_count` | int      | Number of top candidates in this report          |
| `sheet_rows_count`     | int      | Number of rows ready for Sheets export           |
| `warnings`             | array    | Non-fatal issues (e.g. missing signals)          |
| `errors`               | array    | Fatal issues blocking delivery                   |
| `email_subject`        | string   | Ready-to-use email subject line                  |
| `email_body_text`      | string   | Plain text email body                            |
| `email_body_html`      | string   | HTML email body (no external CSS or scripts)     |
| `sheet_rows`           | array    | Rows for Google Sheets / CSV export              |
| `n8n_payload`          | object   | Compact subset for n8n nodes                     |
| `future_integrations`  | object   | Planned integrations — status: "planned"         |

---

## Future Integrations (Not Active Yet)

These signals and delivery channels are planned but not yet connected.
They are listed in `future_integrations` with `status: "planned"` and
`current_behavior: "not connected yet"`.

| Integration           | Purpose                                          | Credentials needed |
|-----------------------|--------------------------------------------------|--------------------|
| google_trends         | Trend interest, direction, seasonality           | No                 |
| amazon_or_keepa       | BSR, competitor count, review volume             | Yes                |
| social_tiktok_meta    | TikTok views, momentum, Meta advertisers         | Yes                |
| reddit_youtube        | Buyer pain point signals                         | Yes                |
| supplier_sources      | Supplier cost, AliExpress count, lead time       | No                 |
| google_sheets         | Direct sheet append via Sheets API               | Yes                |
| email                 | Direct email via SMTP or Gmail API               | Yes                |
| notion                | Notion database sync                             | Yes                |

When a future integration is ready, update `backend/sources/registry.py`
to set its `status` to `"active"` and wire the connector in
`backend/sources/`.

---

## Existing Workflows

| File                                                    | Phase   | Status  |
|---------------------------------------------------------|---------|---------|
| `auto-discovery-daily-report-phase-2c-a.json`           | 2C-A    | Working |
| `auto-discovery-daily-report-phase-2c-b-ebay-sandbox.json` | 2C-B | Working |
| `auto-discovery-daily-report-phase-2c-c-scoring-report.json` | 2C-C | Working |

These workflows call `/sources/ebay/discover` and `/reports/daily`.
They are not affected by Phase 2F-D changes.

To wire the new delivery flow, create a new n8n workflow that:
1. Calls `GET /reports/daily/delivery/health` (HTTP Request node)
2. Checks `ok == true` (IF node)
3. On true: calls `GET /reports/daily/delivery` and routes the payload to Email / Sheets / Notion nodes
4. On false: sends an alert notification
