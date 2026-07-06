"""Official Google Trends connector — Phase 2G-E.

Uses only official Google / Google Cloud APIs. No pytrends. No web scraping.
No undocumented API calls.

The Google Trends API is currently in alpha (access-gated). It was announced in
July 2025. Full documentation and endpoints are only accessible after alpha invitation.
No API calls are made until GOOGLE_TRENDS_OFFICIAL_ACCESS_MODE=confirmed and valid
Google Cloud credentials are configured.

Application: https://developers.google.com/search/apis/trends

Status values:
  pending_access      default — alpha access not yet applied for or approved
  missing_credentials alpha access confirmed but GOOGLE_CLOUD_PROJECT_ID or
                      GOOGLE_APPLICATION_CREDENTIALS is absent
  ready               alpha access approved, all credentials configured
                      (set GOOGLE_TRENDS_OFFICIAL_ACCESS_MODE=confirmed)
"""
import os
from .base import BaseConnector


class GoogleTrendsOfficialConnector(BaseConnector):
    name = "google_trends"
    label = "Google Trends API (Official — alpha access pending)"
    implemented = False  # implementation pending official alpha access approval
    requires_credentials = True
    required_env_vars = [
        "GOOGLE_CLOUD_PROJECT_ID",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ]
    signal_types_supported = ["trend", "demand"]
    recommended_priority = 1
    current_behavior = (
        "Status: pending_access — Google Trends API is in alpha (announced July 2025). "
        "Full API documentation and endpoints are only accessible after invitation. "
        "No live calls until GOOGLE_TRENDS_OFFICIAL_ACCESS_MODE=confirmed and "
        "valid Google Cloud credentials are configured. "
        "No pytrends, no scraping, no unofficial clients."
    )
    notes = (
        "Official Google Trends API — alpha / access-gated as of July 2025. "
        "Apply at: https://developers.google.com/search/apis/trends "
        "Google prioritizes applicants with a clear use case who can start testing soon. "
        "Once approved: set GOOGLE_CLOUD_PROJECT_ID + GOOGLE_APPLICATION_CREDENTIALS + "
        "GOOGLE_TRENDS_OFFICIAL_ACCESS_MODE=confirmed."
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
        # Only report credential vars as missing — access_mode is a state, not a credential.
        # Alpha access itself is not an env var; it requires Google's approval.
        missing = []
        if not self._has_project():
            missing.append("GOOGLE_CLOUD_PROJECT_ID")
        if not self._has_credentials():
            missing.append("GOOGLE_APPLICATION_CREDENTIALS")
        return missing

    @property
    def status(self) -> str:
        # Alpha access not yet approved → pending_access (default state)
        # Only progresses past pending_access when access mode is explicitly confirmed.
        if self._access_mode() != "confirmed":
            return "pending_access"
        if not self._has_project() or not self._has_credentials():
            return "missing_credentials"
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

        access_confirmed = access_mode == "confirmed"

        readiness_steps = []
        if not access_confirmed:
            readiness_steps.append(
                "Apply for Google Trends API alpha access at "
                "https://developers.google.com/search/apis/trends — "
                "Describe your use case. Google prioritizes developers who can start testing soon."
            )
            readiness_steps.append(
                "Once approved, set GOOGLE_TRENDS_OFFICIAL_ACCESS_MODE=confirmed in .env"
            )
        if access_confirmed and not has_project:
            readiness_steps.append("Set GOOGLE_CLOUD_PROJECT_ID=<your-gcp-project-id> in .env")
        if access_confirmed and not has_creds:
            readiness_steps.append("Set GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json in .env")

        return {
            "name": self.name,
            "label": self.label,
            "status": current_status,
            "implemented": self.implemented,
            "official_api": True,
            "requires_approval": True,
            "access_pending": current_status == "pending_access",
            "live_call_confirmed": False,
            "can_fetch_real_data": current_status == "ready",
            "data_type": "trend_signal",
            "requires_credentials": self.requires_credentials,
            "required_env_vars": self.required_env_vars,
            "missing_env_vars": self._missing_env_vars(),
            "signal_types_supported": self.signal_types_supported,
            "current_behavior": self.current_behavior,
            "notes": self.notes,
            "alpha_program": {
                "announced": "July 2025",
                "apply_url": "https://developers.google.com/search/apis/trends",
                "docs_gated": True,
                "docs_note": (
                    "Full API documentation and endpoints are only accessible after "
                    "receiving an alpha invitation. The docs page returns 404 or requires "
                    "login with the invited email address."
                ),
                "selection_criteria": (
                    "Google prioritizes: (1) clear use case, "
                    "(2) ability to start testing soon, "
                    "(3) willingness to provide direct feedback."
                ),
                "data_available": (
                    "5 years rolling data, daily/weekly/monthly/yearly aggregations, "
                    "regional analysis (country + sub-region), consistently scaled "
                    "interest scores — compare dozens of terms vs. 8 in the web UI."
                ),
            },
            "config": {
                "access_mode": access_mode,
                "access_confirmed": access_confirmed,
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
