"""Official eBay Browse API connector — Phase 3A.

Uses only the official eBay Browse API via OAuth client-credentials flow
(see backend/sources/ebay.py for the actual HTTP/OAuth implementation).
No scraping. No unofficial endpoints.

This module adds an explicit, conservative live-mode gate on top of the
existing eBay collector: no real eBay request is ever made unless the
operator deliberately sets EBAY_LIVE_ENABLED=true in addition to providing
valid credentials. When the gate is not satisfied, search_items() returns a
clear readiness explanation instead of fake or fabricated data.

Status values:
  disabled            EBAY_LIVE_ENABLED=false (default) — no request is made
  missing_credentials enabled=true but EBAY_CLIENT_ID or EBAY_CLIENT_SECRET
                      is absent
  access_required     credentials present; EBAY_ENVIRONMENT=production
                      (eBay requires an approved production keyset before
                      production traffic is allowed — sandbox needs no
                      additional approval)
  ready               live enabled, credentials present, sandbox environment
"""
import os
from typing import Any, Dict

from .base import BaseConnector


class EbayOfficialConnector(BaseConnector):
    name = "ebay"
    label = "eBay Browse API"
    implemented = True
    requires_credentials = True
    required_env_vars = ["EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"]
    signal_types_supported = ["demand", "competition", "supplier"]
    recommended_priority = 0  # already active — excluded from next_sources_to_connect
    current_behavior = (
        "Live eBay calls are gated behind EBAY_LIVE_ENABLED. When disabled or "
        "credentials are missing, no eBay request is made — search_items() returns "
        "a readiness explanation instead of fake data, and /discovery/multisource "
        "uses stub data in this case."
    )
    notes = (
        "Official eBay Browse API only — OAuth client credentials flow, no scraping. "
        "Set EBAY_LIVE_ENABLED=true plus EBAY_CLIENT_ID and EBAY_CLIENT_SECRET to enable. "
        "EBAY_ENVIRONMENT=production additionally requires an approved eBay production "
        "keyset before live production traffic is allowed."
    )

    # ---------------------------------------------------------------------- helpers

    def _is_live_enabled(self) -> bool:
        return os.environ.get("EBAY_LIVE_ENABLED", "false").strip().lower() in ("true", "1", "yes")

    def _has_client_id(self) -> bool:
        return bool(os.environ.get("EBAY_CLIENT_ID", "").strip())

    def _has_client_secret(self) -> bool:
        return bool(os.environ.get("EBAY_CLIENT_SECRET", "").strip())

    def _environment(self) -> str:
        return os.environ.get("EBAY_ENVIRONMENT", "sandbox").strip().lower()

    def _marketplace_id(self) -> str:
        return os.environ.get("EBAY_MARKETPLACE_ID", "EBAY_US").strip()

    # ---------------------------------------------------------------------- base overrides

    def _missing_env_vars(self) -> list:
        missing = []
        if not self._has_client_id():
            missing.append("EBAY_CLIENT_ID")
        if not self._has_client_secret():
            missing.append("EBAY_CLIENT_SECRET")
        return missing

    @property
    def status(self) -> str:
        if not self._is_live_enabled():
            return "disabled"
        if not self._has_client_id() or not self._has_client_secret():
            return "missing_credentials"
        if self._environment() == "production":
            return "access_required"
        return "ready"

    def check(self) -> dict:
        live_enabled = self._is_live_enabled()
        has_id = self._has_client_id()
        has_secret = self._has_client_secret()
        environment = self._environment()
        marketplace_id = self._marketplace_id()
        current_status = self.status

        readiness_steps = []
        if not live_enabled:
            readiness_steps.append("Set EBAY_LIVE_ENABLED=true in .env to allow live eBay calls.")
        if not has_id:
            readiness_steps.append("Set EBAY_CLIENT_ID=<your eBay app client id> in .env.")
        if not has_secret:
            readiness_steps.append("Set EBAY_CLIENT_SECRET=<your eBay app client secret> in .env.")
        if live_enabled and has_id and has_secret and environment == "production":
            readiness_steps.append(
                "EBAY_ENVIRONMENT=production requires an approved eBay production keyset. "
                "Use EBAY_ENVIRONMENT=sandbox for testing without additional approval."
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
                "live_enabled": live_enabled,
                "environment": environment,
                "marketplace_id": marketplace_id,
                "client_id_set": has_id,
                "client_secret_set": has_secret,
            },
            "readiness_steps": readiness_steps,
        }

    # ---------------------------------------------------------------------- readiness text

    def readiness_reason(self, status: str = None) -> str:
        """Human-readable explanation for why eBay live mode is not active."""
        status = status or self.status
        return {
            "disabled": (
                "eBay live mode is disabled (EBAY_LIVE_ENABLED is not true). "
                "No request was sent to eBay."
            ),
            "missing_credentials": (
                "EBAY_LIVE_ENABLED is true but EBAY_CLIENT_ID and/or EBAY_CLIENT_SECRET "
                "are not set. No request was sent to eBay."
            ),
            "access_required": (
                "EBAY_ENVIRONMENT=production requires an approved eBay production keyset. "
                "No request was sent to eBay. Use EBAY_ENVIRONMENT=sandbox for testing."
            ),
            "ready": "eBay live mode is ready.",
        }.get(status, "eBay is not ready.")

    # ---------------------------------------------------------------------- search

    def search_items(self, query: str, country: str = "US", limit: int = 10) -> Dict[str, Any]:
        """Return eBay search results, or a clear readiness explanation if not ready.

        Never raises — network/auth errors are caught and returned as a structured
        error object so callers (discovery endpoints) never crash.
        """
        current_status = self.status
        if current_status != "ready":
            return {
                "ok": False,
                "source": "ebay",
                "status": current_status,
                "items": [],
                "is_live": False,
                "reason": self.readiness_reason(current_status),
            }

        # Reuse the existing official Browse API OAuth client-credentials flow —
        # same eBay Browse API, gated behind the explicit live-mode check above.
        from sources.ebay import EbayCollector

        try:
            collector = EbayCollector()
            result = collector.discover([query], country=country, limit_per_seed=limit)
            return {
                "ok": True,
                "source": result.get("source", "ebay"),
                "status": current_status,
                "items": result.get("candidates", []),
                "is_live": result.get("source") == "ebay",
                "reason": None,
            }
        except Exception as exc:
            return {
                "ok": False,
                "source": "ebay",
                "status": current_status,
                "items": [],
                "is_live": False,
                "reason": f"eBay request failed ({type(exc).__name__}: {exc}).",
            }
