"""eBay Browse API collector — Phase 2C-B.

Credentials are read exclusively from environment variables (never hardcoded):
  EBAY_CLIENT_ID        OAuth client id
  EBAY_CLIENT_SECRET    OAuth client secret
  EBAY_ENV              'sandbox' | 'production'  (default: sandbox)
  EBAY_FALLBACK_TO_STUB 'true' | 'false'           (default: true)

Modes:
  stub  — EBAY_CLIENT_ID absent → placeholder data returned, risk filter still runs.
  live  — credentials present  → real eBay Browse API called via httpx.
  fallback — live API error + EBAY_FALLBACK_TO_STUB=true → stub data + error note.

Fields not available from eBay Browse API (supplier_cost, TikTok metrics, BSR, …)
are returned as null. The scoring engine treats null as 'Not Measured' and lowers
confidence but never the score.
"""
import base64
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from config import settings

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


# ------------------------------------------------------------------ category mapping

# Maps eBay category names (substrings, lowercase) to our validator's allowed values.
_CATEGORY_MAP: Dict[str, str] = {
    "health": "health",
    "vitamin": "health",
    "medical": "health",
    "wellness": "health",
    "beauty": "beauty",
    "skin care": "beauty",
    "skincare": "beauty",
    "makeup": "beauty",
    "hair care": "beauty",
    "home": "home",
    "garden": "home",
    "storage": "home",
    "organisation": "home",
    "organization": "home",
    "bedding": "home",
    "kitchen": "kitchen",
    "cookware": "kitchen",
    "bakeware": "kitchen",
    "dining": "kitchen",
    "sporting": "fitness",
    "fitness": "fitness",
    "yoga": "fitness",
    "exercise": "fitness",
    "gym": "fitness",
    "pet": "pets",
    "dog": "pets",
    "cat": "pets",
    "automotive": "auto",
    "vehicle": "auto",
    "car care": "auto",
    "toys": "toys",
    "baby": "toys",
    "children": "toys",
    "kid": "toys",
    "cosmetics": "cosmetics",
    "fragrance": "cosmetics",
    "perfume": "cosmetics",
}


def _map_category(ebay_cat: str) -> str:
    """Map a raw eBay category string to one of our validator's allowed values."""
    lowered = ebay_cat.lower().strip()
    if lowered in _CATEGORY_MAP:
        return _CATEGORY_MAP[lowered]
    for key, val in _CATEGORY_MAP.items():
        if key in lowered:
            return val
    return "other"


# ------------------------------------------------------------------ field mapping

def _normalize_candidate(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Map a raw item dict to the shape expected by /discovery/manual (scoring fields)."""
    return {
        "name": raw.get("title", "").strip(),
        "category": raw.get("category", "other"),
        "country": raw.get("country", "US"),
        # link to the live eBay listing — checks source_url/item_url/url/link
        # for compatibility with any naming convention the raw dict may use
        "source_url": raw.get("source_url") or raw.get("item_url") or raw.get("url") or raw.get("link"),
        "item_id": raw.get("item_id"),
        "image_url": raw.get("image_url"),
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


def _ebay_item_to_raw(item: Dict[str, Any], country: str) -> Dict[str, Any]:
    """Map an eBay Browse API item_summary to the intermediate raw dict shape.

    Only fields that eBay actually returns are populated; everything else is None
    so the scoring engine records them as 'Not Measured'.
    """
    price: Optional[float] = None
    try:
        price = float(item.get("price", {}).get("value", ""))
    except (ValueError, TypeError):
        pass

    shipping: Optional[float] = None
    shipping_opts = item.get("shippingOptions", [])
    if shipping_opts:
        try:
            shipping = float(shipping_opts[0].get("shippingCost", {}).get("value", ""))
        except (ValueError, TypeError):
            pass

    category = "other"
    cats = item.get("categories", [])
    if cats:
        raw_cat = cats[0].get("categoryName", "")
        # Try to map the full path, then each segment (broadest first)
        for segment in [raw_cat] + raw_cat.split(" > "):
            mapped = _map_category(segment.strip())
            if mapped != "other":
                category = mapped
                break

    return {
        "title": item.get("title", "").strip(),
        "category": category,
        "country": country,
        "item_url": item.get("itemWebUrl"),
        "item_id": item.get("itemId"),
        "image_url": (item.get("image") or {}).get("imageUrl"),
        "price": price,
        "supplier_cost": None,
        "shipping_cost": shipping,
        "weight_kg": None,
        "trends_interest": None,
        "trends_12mo_change_pct": None,
        "seasonality_peak_trough_ratio": None,
        "amazon_bsr": None,
        "tiktok_hashtag_views": None,
        "tiktok_momentum": None,
        "meta_active_advertisers": None,
        "aliexpress_sellers_1k_orders": None,
        "amazon_competitor_count": None,
        "complementary_skus": None,
        "trends_all_time_current_value": None,
    }


# ------------------------------------------------------------------ collector

class EbayCollector:
    """Wrapper around the eBay Browse API OAuth + item search flow."""

    _TOKEN_URLS = {
        "sandbox":    "https://api.sandbox.ebay.com/identity/v1/oauth2/token",
        "production": "https://api.ebay.com/identity/v1/oauth2/token",
    }
    _SEARCH_URLS = {
        "sandbox":    "https://api.sandbox.ebay.com/buy/browse/v1/item_summary/search",
        "production": "https://api.ebay.com/buy/browse/v1/item_summary/search",
    }
    _MARKETPLACE_IDS: Dict[str, str] = {
        "US": "EBAY_US", "GB": "EBAY_GB", "DE": "EBAY_DE",
        "AU": "EBAY_AU", "CA": "EBAY_CA", "FR": "EBAY_FR",
    }

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        env: Optional[str] = None,
    ) -> None:
        """Defaults preserve the original sandbox-only behavior. Explicit
        client_id/client_secret/env (used by the production-gated path in
        sources/connectors/ebay_official.py) let production calls use
        production credentials without changing the no-arg sandbox default
        used everywhere else."""
        self.client_id: str = client_id if client_id is not None else settings.ebay_client_id
        self.client_secret: str = client_secret if client_secret is not None else settings.ebay_client_secret
        resolved_env = env if env in ("sandbox", "production") else settings.ebay_env
        self.env: str = resolved_env if resolved_env in ("sandbox", "production") else "sandbox"
        self.fallback_to_stub: bool = settings.ebay_fallback_to_stub

        self._token_url: str = self._TOKEN_URLS[self.env]
        self._search_url: str = self._SEARCH_URLS[self.env]

        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # -------------------------------------------------------- auth

    def _credentials_present(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _fetch_token(self) -> Tuple[str, float]:
        """POST to eBay identity endpoint and return (token, expiry_timestamp)."""
        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        with httpx.Client(timeout=10.0) as client:
            resp = client.post(
                self._token_url,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "client_credentials",
                    "scope": "https://api.ebay.com/oauth/api_scope",
                },
            )
        resp.raise_for_status()
        body = resp.json()
        token: str = body["access_token"]
        expires_in: int = int(body.get("expires_in", 7200))
        expires_at: float = time.time() + expires_in - 60  # 60 s safety buffer
        return token, expires_at

    def _ensure_token(self) -> str:
        if self._token is None or time.time() >= self._token_expires_at:
            self._token, self._token_expires_at = self._fetch_token()
        return self._token

    # -------------------------------------------------------- search

    def _search(self, keyword: str, country: str, limit: int) -> List[Dict[str, Any]]:
        """Call eBay Browse API and return raw item_summary dicts."""
        token = self._ensure_token()
        marketplace = self._MARKETPLACE_IDS.get(country.upper(), "EBAY_US")

        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                self._search_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-EBAY-C-MARKETPLACE-ID": marketplace,
                },
                params={"q": keyword, "limit": limit},
            )
        resp.raise_for_status()
        return resp.json().get("itemSummaries", [])

    # -------------------------------------------------------- public interface

    def discover(
        self,
        seeds: List[str],
        country: str = "US",
        limit_per_seed: int = 5,
    ) -> Dict[str, Any]:
        """Return normalized product candidates for the given keyword seeds.

        - No credentials → stub response (risk filter still applied to seeds).
        - Credentials present → live eBay API call.
        - Live call fails + fallback_to_stub=True → stub response with error note.
        - Live call fails + fallback_to_stub=False → exception propagates.
        """
        if not self._credentials_present():
            return _stub_response(seeds, country)

        try:
            return self._live_discover(seeds, country, limit_per_seed)
        except Exception as exc:
            if self.fallback_to_stub:
                result = _stub_response(seeds, country)
                result["source"] = "ebay_stub_fallback"
                result["note"] = (
                    f"eBay API error ({type(exc).__name__}: {exc}) — "
                    "fell back to stub data. "
                    "Set EBAY_FALLBACK_TO_STUB=false to surface errors instead."
                )
                return result
            raise

    def _live_discover(
        self,
        seeds: List[str],
        country: str,
        limit_per_seed: int,
    ) -> Dict[str, Any]:
        candidates: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []

        for seed in seeds:
            if _is_risky(seed):
                skipped.append({"seed": seed, "reason": "blocked keyword"})
                continue
            items = self._search(seed, country=country, limit=limit_per_seed)
            for item in items:
                title = item.get("title", "")
                if _is_risky(title):
                    skipped.append({"seed": seed, "title": title, "reason": "blocked content"})
                    continue
                raw = _ebay_item_to_raw(item, country)
                candidates.append(_normalize_candidate(raw))

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
