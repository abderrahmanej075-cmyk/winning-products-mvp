"""Base class for all external market data source connectors.

Each connector exposes a standard interface so the health endpoint and readiness
planner can work uniformly across all sources without knowing implementation details.
"""
import os


class BaseConnector:
    """Common interface contract for every source connector.

    Class-level attributes describe the connector. Subclasses set them and, when
    the connector is actually implemented, set implemented = True and override any
    logic needed in check().

    Status values:
      active              — implemented and all required credentials are present
      planned             — not yet implemented (connector code does not exist)
      missing_credentials — implemented but one or more required env vars are absent
    """

    name: str = ""
    label: str = ""
    implemented: bool = False
    requires_credentials: bool = False
    required_env_vars: list = []
    signal_types_supported: list = []
    current_behavior: str = "Not connected yet."
    notes: str = ""
    recommended_priority: int = 99  # lower number = connect sooner; 0 = already active

    def _missing_env_vars(self) -> list:
        """Return names of required env vars that are not set or are empty."""
        return [v for v in self.required_env_vars if not os.environ.get(v, "").strip()]

    @property
    def status(self) -> str:
        if not self.implemented:
            return "planned"
        missing = self._missing_env_vars()
        if missing and self.requires_credentials:
            return "missing_credentials"
        return "active"

    def check(self) -> dict:
        """Return a health/readiness dict for this connector.

        This is the primary interface used by GET /sources/connectors/health
        and by build_readiness_plan(). It makes no external API calls.
        """
        missing = self._missing_env_vars()
        return {
            "name": self.name,
            "label": self.label,
            "status": self.status,
            "implemented": self.implemented,
            "requires_credentials": self.requires_credentials,
            "required_env_vars": self.required_env_vars,
            "missing_env_vars": missing,
            "signal_types_supported": self.signal_types_supported,
            "can_fetch_real_data": self.status == "active",
            "current_behavior": self.current_behavior,
            "notes": self.notes,
        }
