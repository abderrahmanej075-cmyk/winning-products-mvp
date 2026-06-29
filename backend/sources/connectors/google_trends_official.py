"""Official Google Trends connector — Phase 2G-E.

Uses only official Google / Google Cloud APIs. No pytrends. No web scraping.
No undocumented API calls.

The Google Trends official API is currently alpha / access-gated. This connector
is disabled by default and makes no API calls unless GOOGLE_TRENDS_OFFICIAL_ENABLED
is set to true and valid Google Cloud credentials are configured.

BigQuery alternative: The public dataset bigquery-public-data.google_trends is
available with a Google Cloud project + BigQuery API enabled. Controlled via
GOOGLE_BIGQUERY_TRENDS_ENABLED. No alpha access required.

Status values:
  disabled            GOOGLE_TRENDS_OFFICIAL_ENABLED=false (default)
  missing_credentials enabled=true but GOOGLE_CLOUD_PROJECT_ID or
                      GOOGLE_APPLICATION_CREDENTIALS is absent
  access_required     credentials present; access_mode=alpha (manual approval
                      from Google required before calls can be made)
  ready               all config, auth, and non-alpha access confirmed
"""
import os
from .base import BaseConnector


class GoogleTrendsOfficialConnector(BaseConnector):
    name = "google_trends"
    label = "Google Trends API (Official / Google Cloud)"
    implemented = False  # implementation pending official alpha access
    requires_credentials = True
    required_env_vars = [
        "GOOGLE_TRENDS_OFFICIAL_ENABLED",
        "GOOGLE_CLOUD_PROJECT_ID",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ]
    signal_types_supported = ["trend", "demand"]
    recommended_priority = 1
    current_behavior = (
        "Disabled by default. Official Google Trends API is alpha/access-gated. "
        "No API calls are made without GOOGLE_TRENDS_OFFICIAL_ENABLED=true and "
        "valid Google Cloud credentials."
    )
    notes = (
        "Official Google Trends API — no pytrends, no scraping. "
        "Alpha access requires approval from Google. "
        "Apply at https://developers.google.com/trends/get-started. "
        "Set GOOGLE_TRENDS_OFFICIAL_ENABLED=true + GOOGLE_CLOUD_PROJECT_ID + "
        "GOOGLE_APPLICATION_CREDENTIALS when access is granted. "
        "Alternative: GOOGLE_BIGQUERY_TRENDS_ENABLED=true uses the BigQuery "
        "public dataset (bigquery-public-data.google_trends) without alpha access."
    )

    # ---------------------------------------------------------------------- helpers

    def _is_enabled(self) -> bool:
        return os.environ.get("GOOGLE_TRENDS_OFFICIAL_ENABLED", "false").lower() in ("true", "1", "yes")

    def _has_project(self) -> bool:
        return bool(os.environ.get("GOOGLE_CLOUD_PROJECT_ID", "").strip())

    def _has_credentials(self) -> bool:
        return bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip())

    def _access_mode(self) -> str:
        return os.environ.get("GOOGLE_TRENDS_OFFICIAL_ACCESS_MODE", "alpha").strip().lower()

    def _is_bigquery_enabled(self) -> bool:
        return os.environ.get("GOOGLE_BIGQUERY_TRENDS_ENABLED", "false").lower() in ("true", "1", "yes")

    # ---------------------------------------------------------------------- base overrides

    def _missing_env_vars(self) -> list:
        missing = []
        if not self._is_enabled():
            missing.append("GOOGLE_TRENDS_OFFICIAL_ENABLED")
        if not self._has_project():
            missing.append("GOOGLE_CLOUD_PROJECT_ID")
        if not self._has_credentials():
            missing.append("GOOGLE_APPLICATION_CREDENTIALS")
        return missing

    @property
    def status(self) -> str:
        if not self._is_enabled():
            return "disabled"
        if not self._has_project() or not self._has_credentials():
            return "missing_credentials"
        if self._access_mode() == "alpha":
            return "access_required"
        return "ready"

    def check(self) -> dict:
        enabled = self._is_enabled()
        has_project = self._has_project()
        has_creds = self._has_credentials()
        access_mode = self._access_mode()
        bigquery_enabled = self._is_bigquery_enabled()
        bigquery_dataset = os.environ.get(
            "GOOGLE_BIGQUERY_TRENDS_DATASET", "bigquery-public-data.google_trends"
        )
        current_status = self.status

        bigquery_status = "disabled"
        if bigquery_enabled and has_project:
            bigquery_status = "ready"
        elif bigquery_enabled and not has_project:
            bigquery_status = "missing_credentials"

        readiness_steps = []
        if not enabled:
            readiness_steps.append("Set GOOGLE_TRENDS_OFFICIAL_ENABLED=true in .env")
        if not has_project:
            readiness_steps.append("Set GOOGLE_CLOUD_PROJECT_ID=<your-gcp-project-id> in .env")
        if not has_creds:
            readiness_steps.append("Set GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json in .env")
        if enabled and has_project and has_creds and access_mode == "alpha":
            readiness_steps.append(
                "Apply for official Google Trends API alpha access at "
                "https://developers.google.com/trends/get-started"
            )
            readiness_steps.append(
                "Once approved, set GOOGLE_TRENDS_OFFICIAL_ACCESS_MODE=confirmed in .env"
            )

        return {
            "name": self.name,
            "label": self.label,
            "status": current_status,
            "implemented": self.implemented,
            "requires_credentials": self.requires_credentials,
            "required_env_vars": self.required_env_vars,
            "missing_env_vars": self._missing_env_vars(),
            "signal_types_supported": self.signal_types_supported,
            "can_fetch_real_data": current_status == "ready",
            "current_behavior": self.current_behavior,
            "notes": self.notes,
            "config": {
                "enabled": enabled,
                "access_mode": access_mode,
                "geo": os.environ.get("GOOGLE_TRENDS_OFFICIAL_GEO", "US"),
                "timeframe": os.environ.get("GOOGLE_TRENDS_OFFICIAL_TIMEFRAME", "today 12-m"),
                "timeout_seconds": int(os.environ.get("GOOGLE_TRENDS_OFFICIAL_TIMEOUT_SECONDS", "10")),
                "project_id_set": has_project,
                "credentials_set": has_creds,
            },
            "bigquery_alternative": {
                "status": bigquery_status,
                "enabled": bigquery_enabled,
                "dataset": bigquery_dataset,
                "notes": (
                    "BigQuery public dataset (bigquery-public-data.google_trends) "
                    "requires only a Google Cloud project + BigQuery API enabled. "
                    "No alpha access needed. Set GOOGLE_BIGQUERY_TRENDS_ENABLED=true to use."
                ),
            },
            "readiness_steps": readiness_steps,
        }
