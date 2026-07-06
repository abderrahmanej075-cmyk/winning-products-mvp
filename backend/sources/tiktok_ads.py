"""TikTok Ads Intelligence collector.

Credentials are read exclusively from environment variables (never hardcoded):
  TIKTOK_API_PROVIDER   Provider mode — controls which endpoint shape is used.
                        Values: placeholder | mock | third_party
                        Default: placeholder (no live calls attempted)
  TIKTOK_API_TOKEN      Bearer token for the configured provider.
  TIKTOK_API_BASE_URL   Base URL for the API.
  TIKTOK_FALLBACK_TO_STUB  'true' | 'false' (default: true)

Provider modes
--------------
  placeholder   (default)
      No live endpoint is configured. Stub data is always returned.
      The TikTok for Business API (business-api.tiktok.com) does NOT expose
      a product search endpoint — it manages ad campaigns, not product browsing.
      Setting a token with provider=placeholder will NOT make live calls.

  mock
      A user-controlled local or test HTTP server at TIKTOK_API_BASE_URL.
      Useful for integration testing without real credentials.
      Expected endpoint: GET {base}/products/search
      Expected response: {"data": {"products": [{"title": ..., "price": ..., ...}]}}

  third_party
      A paid ad-intelligence platform (Minea, Pipiads, BigSpy, AdSpy, etc.)
      that exposes a product search REST API.
      Set TIKTOK_API_BASE_URL to the provider's base URL.
      Set TIKTOK_API_TOKEN to the provider's API key / Bearer token.
      Endpoint shape varies by provider — check provider docs for exact paths.

No scraping. No access-rule bypass. Official TikTok APIs do not expose
a usable product search endpoint for this use case as of 2026-07-05.
"""
import json
import os
import pathlib
import re
from typing import Any, Dict, List, Optional

import httpx

# ------------------------------------------------------------------ live flag file
# Written by POST /sources/tiktok_ads/verify when a real call succeeds.
# The connector reads this to automatically set status=active.
# Contains NO secrets — only metadata (provider, timestamps, counts).
LIVE_FLAG_FILE: pathlib.Path = pathlib.Path(__file__).parent.parent / ".tiktok_ads_live_confirmed.json"


def read_live_flag() -> Optional[Dict[str, Any]]:
    """Return the contents of the live confirmation flag, or None if absent."""
    try:
        return json.loads(LIVE_FLAG_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_live_flag(data: Dict[str, Any]) -> None:
    """Persist live confirmation metadata. Never writes tokens or secrets."""
    safe = {k: v for k, v in data.items() if k not in ("token", "base_url")}
    LIVE_FLAG_FILE.write_text(json.dumps(safe, indent=2), encoding="utf-8")

# Providers that support live discovery calls.
# 'placeholder' and anything unrecognised always falls back to stub.
_LIVE_PROVIDERS: frozenset = frozenset({"mock", "third_party"})

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


# ------------------------------------------------------------------ stub data

_STUB_ITEMS: List[Dict[str, Any]] = [
    {
        "name": "Magnetic Wireless Phone Mount",
        "category": "auto",
        "country": "US",
        "retail_price": 29.99,
        "supplier_cost": 7.50,
        "shipping_cost": 2.80,
        "product_weight_kg": 0.12,
        "tiktok_hashtag_views": 120_000_000,
        "tiktok_momentum": "surging",
        "meta_active_advertisers": 18,
        "trends_interest": 68,
        "trends_direction_pct": 32.0,
        "aliexpress_sellers_1k": 4,
        "competitor_count": 750,
        "source_url": None,
    },
    {
        "name": "Portable Mini Blender Cup",
        "category": "kitchen",
        "country": "US",
        "retail_price": 24.99,
        "supplier_cost": 5.80,
        "shipping_cost": 3.10,
        "product_weight_kg": 0.28,
        "tiktok_hashtag_views": 95_000_000,
        "tiktok_momentum": "surging",
        "meta_active_advertisers": 14,
        "trends_interest": 74,
        "trends_direction_pct": 25.0,
        "aliexpress_sellers_1k": 6,
        "competitor_count": 620,
        "source_url": None,
    },
    {
        "name": "RGB Smart LED Strip Lights",
        "category": "home",
        "country": "US",
        "retail_price": 19.99,
        "supplier_cost": 4.20,
        "shipping_cost": 2.50,
        "product_weight_kg": 0.20,
        "tiktok_hashtag_views": 200_000_000,
        "tiktok_momentum": "rising",
        "meta_active_advertisers": 22,
        "trends_interest": 81,
        "trends_direction_pct": 18.0,
        "aliexpress_sellers_1k": 9,
        "competitor_count": 1_800,
        "source_url": None,
    },
    {
        "name": "Posture Corrector Brace Adjustable",
        "category": "health",
        "country": "US",
        "retail_price": 27.99,
        "supplier_cost": 6.50,
        "shipping_cost": 3.20,
        "product_weight_kg": 0.18,
        "tiktok_hashtag_views": 85_000_000,
        "tiktok_momentum": "surging",
        "meta_active_advertisers": 12,
        "trends_interest": 72,
        "trends_direction_pct": 28.0,
        "aliexpress_sellers_1k": 3,
        "competitor_count": 820,
        "source_url": None,
    },
    {
        "name": "Self-Cleaning Insulated Water Bottle",
        "category": "fitness",
        "country": "US",
        "retail_price": 34.99,
        "supplier_cost": 8.20,
        "shipping_cost": 3.50,
        "product_weight_kg": 0.35,
        "tiktok_hashtag_views": 60_000_000,
        "tiktok_momentum": "rising",
        "meta_active_advertisers": 9,
        "trends_interest": 65,
        "trends_direction_pct": 21.0,
        "aliexpress_sellers_1k": 5,
        "competitor_count": 980,
        "source_url": None,
    },
]


def _stub_response(seeds: List[str], country: str, note: str = "") -> Dict[str, Any]:
    clean_seeds = [s for s in seeds if not _is_risky(s)]
    risky_seeds = [{"seed": s, "reason": "blocked keyword"} for s in seeds if _is_risky(s)]

    candidates: List[Dict[str, Any]] = []
    if clean_seeds:
        for item in _STUB_ITEMS:
            candidates.append({**item, "country": country})

    return {
        "candidates": candidates,
        "skipped": risky_seeds,
        "source": "tiktok_ads_stub",
        "note": note or (
            "TIKTOK_API_TOKEN not set or provider=placeholder — "
            "returning stub ad-intelligence data."
        ),
    }


# ------------------------------------------------------------------ field mapping

def _map_live_item(item: Dict[str, Any], country: str) -> Dict[str, Any]:
    """Map a third-party or mock provider product item to the scoring-field shape.

    Field names are checked in order of preference to accommodate different
    provider response shapes without requiring per-provider parsers.
    """
    return {
        "name": (item.get("title") or item.get("name") or item.get("productName") or "").strip(),
        "category": item.get("category", "other"),
        "country": country,
        "retail_price": item.get("price") or item.get("retail_price") or item.get("sellPrice"),
        "supplier_cost": item.get("supplier_cost") or item.get("sourcePrice"),
        "shipping_cost": item.get("shipping_cost") or item.get("shippingCost"),
        "product_weight_kg": item.get("weight_kg") or item.get("productWeight"),
        "tiktok_hashtag_views": item.get("hashtag_views") or item.get("tiktok_hashtag_views"),
        "tiktok_momentum": item.get("momentum") or item.get("tiktok_momentum"),
        "meta_active_advertisers": item.get("meta_active_advertisers"),
        "trends_interest": item.get("trends_interest"),
        "trends_direction_pct": item.get("trends_direction_pct"),
        "aliexpress_sellers_1k": item.get("aliexpress_sellers_1k"),
        "competitor_count": item.get("competitor_count"),
        "source_url": item.get("url") or item.get("source_url") or item.get("product_url") or item.get("adUrl"),
        "item_id": str(item["id"]) if item.get("id") else None,
    }


# ------------------------------------------------------------------ collector


class TikTokAdsCollector:
    """TikTok Ads Intelligence collector.

    Always returns stub data when provider=placeholder (the default).
    Attempts live calls only for provider=mock or provider=third_party.
    """

    def __init__(self) -> None:
        self.provider: str = os.getenv("TIKTOK_API_PROVIDER", "placeholder").strip().lower()
        self.token: str = os.getenv("TIKTOK_API_TOKEN", "").strip()
        self.base_url: str = os.getenv("TIKTOK_API_BASE_URL", "").strip()
        self.fallback_to_stub: bool = (
            os.getenv("TIKTOK_FALLBACK_TO_STUB", "true").lower() in ("true", "1", "yes")
        )

    def _can_attempt_live(self) -> bool:
        """True only when a real provider and token are both configured."""
        return (
            self.provider in _LIVE_PROVIDERS
            and bool(self.token)
            and bool(self.base_url)
        )

    # Keep _has_credentials() for backwards-compat with dispatch code in main.py
    def _has_credentials(self) -> bool:
        return self._can_attempt_live()

    def discover(
        self,
        seeds: List[str],
        country: str = "US",
        limit_per_seed: int = 5,
    ) -> Dict[str, Any]:
        if not self._can_attempt_live():
            if self.provider == "placeholder":
                note = (
                    "provider=placeholder (default) — no live TikTok product search endpoint exists. "
                    "Set TIKTOK_API_PROVIDER=third_party and configure a real provider to enable live data."
                )
            elif self.provider in _LIVE_PROVIDERS and not self.token:
                note = (
                    f"provider={self.provider} configured but TIKTOK_API_TOKEN is not set. "
                    "Returning stub data."
                )
            elif self.provider in _LIVE_PROVIDERS and not self.base_url:
                note = (
                    f"provider={self.provider} configured but TIKTOK_API_BASE_URL is not set. "
                    "Returning stub data."
                )
            else:
                note = f"provider={self.provider} — not a recognised live provider. Returning stub data."
            return _stub_response(seeds, country, note=note)

        try:
            return self._live_discover(seeds, country, limit_per_seed)
        except Exception as exc:
            if self.fallback_to_stub:
                result = _stub_response(
                    seeds, country,
                    note=(
                        f"provider={self.provider} API error "
                        f"({type(exc).__name__}: {exc}) — fell back to stub data."
                    ),
                )
                result["source"] = "tiktok_ads_stub_fallback"
                return result
            raise

    def _live_discover(
        self,
        seeds: List[str],
        country: str,
        limit_per_seed: int,
    ) -> Dict[str, Any]:
        """Call the configured provider's product search endpoint.

        Endpoint shape expected (provider must conform):
          GET {TIKTOK_API_BASE_URL}/products/search
          Headers: Authorization: Bearer {TIKTOK_API_TOKEN}
          Params:  keyword=<str>, country=<str>, limit=<int>
          Response: {"data": {"products": [{"title": ..., "price": ..., ...}]}}
        """
        candidates: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []

        with httpx.Client(timeout=15.0) as client:
            for seed in seeds:
                if _is_risky(seed):
                    skipped.append({"seed": seed, "reason": "blocked keyword"})
                    continue
                try:
                    resp = client.get(
                        f"{self.base_url}/products/search",
                        headers={"Authorization": f"Bearer {self.token}"},
                        params={"keyword": seed, "country": country, "limit": limit_per_seed},
                    )
                    resp.raise_for_status()
                    items = resp.json().get("data", {}).get("products", [])
                    for item in items:
                        title = item.get("title") or item.get("name") or ""
                        if _is_risky(title):
                            skipped.append({"seed": seed, "title": title, "reason": "blocked content"})
                            continue
                        candidates.append(_map_live_item(item, country))
                except Exception as exc:
                    skipped.append({"seed": seed, "reason": f"api_error: {exc}"})

        return {
            "candidates": candidates,
            "skipped": skipped,
            "source": "tiktok_ads",
            "provider": self.provider,
        }
