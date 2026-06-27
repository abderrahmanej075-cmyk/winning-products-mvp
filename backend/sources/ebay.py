"""eBay Browse API collector — Phase 2C auto-discovery stub.

Credentials are read from environment variables (never hardcoded):
  EBAY_CLIENT_ID      OAuth client id
  EBAY_CLIENT_SECRET  OAuth client secret
  EBAY_ENV            'sandbox' | 'production'  (default: sandbox)

When EBAY_CLIENT_ID is absent, discover() returns safe placeholder data so
the full pipeline (risk filter -> /discovery/manual) can be exercised without
real credentials.

Real OAuth + Browse API wiring is left as NotImplementedError until credentials
are available.
"""
import os
import re
from typing import Any, Dict, List, Optional

# ------------------------------------------------------------------ risk guard

BLOCKED_TERMS: frozenset = frozenset({
    "vape", "nicotine", "alcohol", "weapons", "gun", "knife",
    "pepper spray", "supplement", "pills", "adult", "casino",
    "gambling", "counterfeit",
})


def _is_risky(text: str) -> bool:
    lowered = text.lower()
    for term in BLOCKED_TERMS:
        if re.search(r"\b" + re.escape(term) + r"\b", lowered):
            return True
    return False


# ------------------------------------------------------------------ field mapping

def _normalize_candidate(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Map raw eBay item dict to the shape expected by /discovery/manual (scoring fields)."""
    return {
        "name": raw.get("title", "").strip(),
        "category": raw.get("category", "other"),
        "country": raw.get("country", "US"),
        # profit
        "retail_price": raw.get("price"),
        "supplier_cost": raw.get("supplier_cost"),
        "shipping_cost": raw.get("shipping_cost"),
        "product_weight_kg": raw.get("weight_kg"),
        # demand / trend
        "trends_interest": raw.get("trends_interest"),
        "trends_direction_pct": raw.get("trends_12mo_change_pct"),
        "seasonality_ratio": raw.get("seasonality_peak_trough_ratio"),
        "amazon_bsr": raw.get("amazon_bsr"),
        # content
        "tiktok_hashtag_views": raw.get("tiktok_hashtag_views"),
        "tiktok_momentum": raw.get("tiktok_momentum"),
        "meta_active_advertisers": raw.get("meta_active_advertisers"),
        # competition
        "aliexpress_sellers_1k": raw.get("aliexpress_sellers_1k_orders"),
        "competitor_count": raw.get("amazon_competitor_count"),
        # differentiation
        "diff_complement_skus": raw.get("complementary_skus"),
        # all-time trend anchor
        "alltime_current_value": raw.get("trends_all_time_current_value"),
    }


# ------------------------------------------------------------------ collector

class EbayCollector:
    """Thin wrapper around the eBay Browse API OAuth + search flow."""

    SANDBOX_BASE = "https://api.sandbox.ebay.com"
    PROD_BASE = "https://api.ebay.com"

    def __init__(self):
        self.client_id: str = os.environ.get("EBAY_CLIENT_ID", "")
        self.client_secret: str = os.environ.get("EBAY_CLIENT_SECRET", "")
        self.env: str = os.environ.get("EBAY_ENV", "sandbox").lower()
        self.base_url: str = self.SANDBOX_BASE if self.env == "sandbox" else self.PROD_BASE
        self._token: Optional[str] = None

    def _credentials_present(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _fetch_token(self) -> str:
        """Exchange client credentials for an OAuth application token.

        Real implementation:
          POST {base_url}/identity/v1/oauth2/token
          Authorization: Basic base64(client_id:client_secret)
          Body: grant_type=client_credentials
                &scope=https://api.ebay.com/oauth/api_scope
        """
        raise NotImplementedError(
            "Real eBay OAuth not wired yet — set EBAY_CLIENT_ID and EBAY_CLIENT_SECRET"
        )

    def _search(self, keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Call eBay Browse API /buy/browse/v1/item_summary/search.

        Real implementation:
          GET {base_url}/buy/browse/v1/item_summary/search
              ?q={keyword}&limit={limit}
          Authorization: Bearer {token}
        """
        raise NotImplementedError("Real eBay search not wired yet")

    def discover(
        self,
        seeds: List[str],
        country: str = "US",
        limit_per_seed: int = 5,
    ) -> Dict[str, Any]:
        """Return normalized product candidates for the given keyword seeds.

        Without credentials returns stub data. With credentials, calls the real
        Browse API (not wired until _fetch_token / _search are implemented).
        """
        if not self._credentials_present():
            return _stub_response(seeds, country)

        if self._token is None:
            self._token = self._fetch_token()

        candidates: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []

        for seed in seeds:
            if _is_risky(seed):
                skipped.append({"seed": seed, "reason": "blocked keyword"})
                continue
            raw_items = self._search(seed, limit=limit_per_seed)
            for item in raw_items:
                title = item.get("title", "")
                if _is_risky(title):
                    skipped.append({"seed": seed, "title": title, "reason": "blocked content"})
                    continue
                candidates.append(_normalize_candidate({**item, "country": country}))

        return {
            "candidates": candidates,
            "skipped": skipped,
            "source": "ebay",
            "env": self.env,
        }


# ------------------------------------------------------------------ stub data

_STUB_ITEMS: List[Dict[str, Any]] = [
    {
        "title": "Posture Corrector Back Brace",
        "category": "health",
        "price": 29.99,
        "supplier_cost": 6.50,
        "shipping_cost": 3.20,
        "weight_kg": 0.18,
        "trends_interest": 72,
        "trends_12mo_change_pct": 28.0,
        "seasonality_peak_trough_ratio": 1.3,
        "amazon_bsr": 4200,
        "tiktok_hashtag_views": 85_000_000,
        "tiktok_momentum": "surging",
        "meta_active_advertisers": 12,
        "aliexpress_sellers_1k_orders": 3,
        "amazon_competitor_count": 820,
        "complementary_skus": 2,
        "trends_all_time_current_value": 68,
    },
    {
        "title": "Reusable Silicone Food Bag Set",
        "category": "kitchen",
        "price": 19.99,
        "supplier_cost": 4.10,
        "shipping_cost": 2.50,
        "weight_kg": 0.22,
        "trends_interest": 55,
        "trends_12mo_change_pct": 15.0,
        "seasonality_peak_trough_ratio": 1.1,
        "amazon_bsr": 11_000,
        "tiktok_hashtag_views": 22_000_000,
        "tiktok_momentum": "rising",
        "meta_active_advertisers": 7,
        "aliexpress_sellers_1k_orders": 5,
        "amazon_competitor_count": 1500,
        "complementary_skus": 3,
        "trends_all_time_current_value": 52,
    },
]


def _stub_response(seeds: List[str], country: str) -> Dict[str, Any]:
    clean_seeds = [s for s in seeds if not _is_risky(s)]
    risky_seeds = [{"seed": s, "reason": "blocked keyword"} for s in seeds if _is_risky(s)]

    candidates: List[Dict[str, Any]] = []
    if clean_seeds:
        for item in _STUB_ITEMS:
            candidates.append(_normalize_candidate({**item, "country": country}))

    return {
        "candidates": candidates,
        "skipped": risky_seeds,
        "source": "ebay_stub",
        "env": "stub",
        "note": (
            "EBAY_CLIENT_ID not set — returning placeholder data. "
            "Set EBAY_CLIENT_ID + EBAY_CLIENT_SECRET to enable live collection."
        ),
    }
