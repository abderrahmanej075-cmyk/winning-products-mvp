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
  missing_credentials enabled=true but EBAY_CLIENT_ID/EBAY_CLIENT_SECRET (sandbox)
                      or EBAY_PRODUCTION_CLIENT_ID/EBAY_PRODUCTION_CLIENT_SECRET
                      (production) are absent
  access_required     credentials present, EBAY_ENVIRONMENT=production, but
                      EBAY_PRODUCTION_READY has not been explicitly confirmed
                      — see production_readiness() for the detailed breakdown
  ready               all gates for the active environment are satisfied —
                      sandbox needs EBAY_LIVE_ENABLED + sandbox credentials;
                      production additionally needs EBAY_PRODUCTION_READY=true
                      plus EBAY_PRODUCTION_CLIENT_ID/SECRET

Phase 3D — production is enabled ONLY when all four gates pass simultaneously:
EBAY_ENVIRONMENT=production, EBAY_PRODUCTION_READY=true,
EBAY_PRODUCTION_CLIENT_ID set, EBAY_PRODUCTION_CLIENT_SECRET set. Production
calls always use the production credentials (never the sandbox ones), and
sandbox calls always use the sandbox credentials (never the production ones)
— see search_items() and sources/ebay.py's EbayCollector constructor.
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
        "Set EBAY_LIVE_ENABLED=true plus EBAY_CLIENT_ID and EBAY_CLIENT_SECRET to enable "
        "sandbox. EBAY_ENVIRONMENT=production additionally requires EBAY_PRODUCTION_CLIENT_ID, "
        "EBAY_PRODUCTION_CLIENT_SECRET, and EBAY_PRODUCTION_READY=true, all set at once, "
        "before live production traffic is allowed."
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

    def _has_production_client_id(self) -> bool:
        return bool(os.environ.get("EBAY_PRODUCTION_CLIENT_ID", "").strip())

    def _has_production_client_secret(self) -> bool:
        return bool(os.environ.get("EBAY_PRODUCTION_CLIENT_SECRET", "").strip())

    def _is_production_ready_confirmed(self) -> bool:
        return os.environ.get("EBAY_PRODUCTION_READY", "false").strip().lower() in ("true", "1", "yes")

    def _production_calls_allowed(self) -> bool:
        """All four production gates must hold simultaneously."""
        return (
            self._environment() == "production"
            and self._is_production_ready_confirmed()
            and self._has_production_client_id()
            and self._has_production_client_secret()
        )

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
        if self._environment() == "production":
            if not self._has_production_client_id() or not self._has_production_client_secret():
                return "missing_credentials"
            if not self._is_production_ready_confirmed():
                return "access_required"
            return "ready"
        if not self._has_client_id() or not self._has_client_secret():
            return "missing_credentials"
        return "ready"

    def production_readiness(self) -> dict:
        """Production-credential readiness, independent of EBAY_LIVE_ENABLED.

        production_calls_allowed is True only when all four gates hold at once:
        EBAY_ENVIRONMENT=production, EBAY_PRODUCTION_READY=true, and both
        production credentials set. Any single missing gate keeps it False.
        """
        has_id = self._has_production_client_id()
        has_secret = self._has_production_client_secret()
        ready_confirmed = self._is_production_ready_confirmed()
        calls_allowed = self._production_calls_allowed()

        if not has_id or not has_secret:
            readiness_status = "production_missing_credentials"
        elif not ready_confirmed:
            readiness_status = "production_access_not_confirmed"
        elif calls_allowed:
            readiness_status = "production_ready"
        else:
            readiness_status = "production_gates_satisfied_pending_environment_switch"

        next_steps = []
        if not has_id:
            next_steps.append(
                "Set EBAY_PRODUCTION_CLIENT_ID in .env only when ready to test production."
            )
        if not has_secret:
            next_steps.append(
                "Set EBAY_PRODUCTION_CLIENT_SECRET in .env only when ready to test production."
            )
        if has_id and has_secret and not ready_confirmed:
            next_steps.append(
                "Set EBAY_PRODUCTION_READY=true in .env once production access has been "
                "confirmed with eBay."
            )
        if has_id and has_secret and ready_confirmed and self._environment() != "production":
            next_steps.append(
                "All production gates are set. Set EBAY_ENVIRONMENT=production in .env to "
                "activate production calls."
            )
        if calls_allowed:
            next_steps.append(
                "Production calls are active. Monitor usage and costs carefully."
            )

        return {
            "production_client_id_set": has_id,
            "production_client_secret_set": has_secret,
            "production_ready_confirmed": ready_confirmed,
            "production_readiness_status": readiness_status,
            "production_calls_allowed": calls_allowed,
            "next_manual_steps": next_steps,
        }

    def check(self) -> dict:
        live_enabled = self._is_live_enabled()
        has_id = self._has_client_id()
        has_secret = self._has_client_secret()
        environment = self._environment()
        marketplace_id = self._marketplace_id()
        current_status = self.status
        prod_readiness = self.production_readiness()

        readiness_steps = []
        if not live_enabled:
            readiness_steps.append("Set EBAY_LIVE_ENABLED=true in .env to allow live eBay calls.")
        if environment == "production":
            readiness_steps.extend(prod_readiness["next_manual_steps"])
        else:
            if not has_id:
                readiness_steps.append("Set EBAY_CLIENT_ID=<your eBay app client id> in .env.")
            if not has_secret:
                readiness_steps.append("Set EBAY_CLIENT_SECRET=<your eBay app client secret> in .env.")

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
            "production_readiness": prod_readiness,
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
                "EBAY_ENVIRONMENT=production requires EBAY_PRODUCTION_CLIENT_ID, "
                "EBAY_PRODUCTION_CLIENT_SECRET, and EBAY_PRODUCTION_READY=true, all set "
                "simultaneously. No request was sent to eBay until all three are set. "
                "Use EBAY_ENVIRONMENT=sandbox for testing without production access."
            ),
            "ready": "eBay live mode is ready for the active environment.",
        }.get(status, "eBay is not ready.")

    # ---------------------------------------------------------------------- search

    def build_collector(self):
        """Return an EbayCollector configured for the currently active environment.

        Centralizes credential selection so every caller (search_items, and
        /discovery/multisource in main.py) gets production credentials for
        production and sandbox credentials for sandbox — never mixed — without
        duplicating the os.environ reads at each call site.
        """
        from sources.ebay import EbayCollector

        if self._environment() == "production":
            return EbayCollector(
                client_id=os.environ.get("EBAY_PRODUCTION_CLIENT_ID", "").strip(),
                client_secret=os.environ.get("EBAY_PRODUCTION_CLIENT_SECRET", "").strip(),
                env="production",
            )
        return EbayCollector()  # sandbox credentials, unchanged default

    def search_items(self, query: str, country: str = "US", limit: int = 10) -> Dict[str, Any]:
        """Return eBay search results, or a clear readiness explanation if not ready.

        Never raises — network/auth errors are caught and returned as a structured
        error object so callers (discovery endpoints) never crash.

        Production calls use production credentials only; sandbox calls use
        sandbox credentials only (see sources/ebay.py EbayCollector). Even when
        status is "ready", a redundant gate re-check runs immediately before any
        production network call, as defense in depth.
        """
        current_status = self.status
        environment = self._environment()

        if current_status != "ready":
            return {
                "ok": False,
                "source": "ebay",
                "status": current_status,
                "items": [],
                "is_live": False,
                "reason": self.readiness_reason(current_status),
            }

        if environment == "production" and not self._production_calls_allowed():
            # Should be unreachable (status == "ready" already implies this), kept
            # as a defense-in-depth check directly before any production call.
            return {
                "ok": False,
                "source": "ebay",
                "status": current_status,
                "items": [],
                "is_live": False,
                "reason": "Production safety gate failed unexpectedly; refusing call.",
            }

        # Reuse the existing official Browse API OAuth client-credentials flow —
        # same eBay Browse API, gated behind the explicit live-mode check above.
        try:
            collector = self.build_collector()
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
