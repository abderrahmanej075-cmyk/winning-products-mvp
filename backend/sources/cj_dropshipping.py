"""CJ Dropshipping API collector.

Credentials are read exclusively from environment variables (never hardcoded):
  CJ_API_TOKEN       Access Token from CJ Dropshipping dashboard (180-day TTL per current CJ docs).
                     Refresh Token TTL: 180 days.
                     Obtain: POST /v1/authentication/getAccessToken with your API Key.
                     Refresh: POST /v1/authentication/refreshAccessToken with Refresh Token.
                     Note: calling getAccessToken multiple times within 24 h returns the
                     same cached token — a new token is only issued after 24 h or logout.
  CJ_API_BASE_URL    Base URL (default: https://developers.cjdropshipping.com/api2.0)
  CJ_FALLBACK_TO_STUB  'true' | 'false' (default: true)

Modes:
  stub — CJ_API_TOKEN absent → 5 curated stub products with supplier/margin data.
  live — token present → GET {base}/v1/product/list called with CJ-Access-Token header.

Confirmed CJ API field availability (as of 2026-07-05, verified from live response):
  productNameEn   product title (English)          ✓ available
  productImage    product image URL                ✓ available  → image_url
  pid             product ID                        ✓ available
  categoryName    category string                   ✓ available
  productWeight   weight in grams                   ✓ available
  sellPrice       price CJ charges the dropshipper  ✓ available → supplier_cost
                  (confirmed live: sellPrice=19.50 vs suggestSellPrice=132.02-212.85)
  suggestSellPrice  CJ suggested retail range       ✗ NOT in list endpoint (detail only)
  sourcePrice       supplier/cost price             ✗ does not exist in CJ API
  productUrl        product detail URL              ✗ NOT returned by CJ API
  productDetailUrl  product detail URL              ✗ NOT returned by CJ API

sellPrice interpretation (resolved 2026-07-05 from live API call):
  sellPrice is what CJ CHARGES the dropshipper when an order is placed.
  It is the supplier cost, not the retail/suggested price.
  suggestSellPrice (range string, detail endpoint only) is CJ's suggested retail.
  retail_price is therefore None in live discovery mode — no reliable retail price
  is available from /v1/product/list. Full margin scoring requires a separate
  detail endpoint call or cross-referencing with market data (eBay, Amazon BSR).
"""
import json
import os
import pathlib
import re
from typing import Any, Dict, List, Optional

import httpx

# ------------------------------------------------------------------ live flag file
# Written by POST /sources/cj_dropshipping/verify when a real call succeeds.
# The connector reads this to automatically set status=active.
# Contains NO secrets — only metadata (timestamps, counts).
CJ_LIVE_FLAG_FILE: pathlib.Path = pathlib.Path(__file__).parent.parent / ".cj_dropshipping_live_confirmed.json"


def read_live_flag() -> Optional[Dict[str, Any]]:
    """Return the contents of the CJ live confirmation flag, or None if absent."""
    try:
        return json.loads(CJ_LIVE_FLAG_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_live_flag(data: Dict[str, Any]) -> None:
    """Persist CJ live confirmation metadata. Never writes tokens or secrets."""
    safe = {k: v for k, v in data.items() if k not in ("token", "base_url")}
    CJ_LIVE_FLAG_FILE.write_text(json.dumps(safe, indent=2), encoding="utf-8")

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


# ------------------------------------------------------------------ category map

_CATEGORY_MAP: Dict[str, str] = {
    "health": "health", "beauty": "beauty", "skin care": "beauty",
    "makeup": "beauty", "hair": "beauty",
    "home": "home", "garden": "home", "bedding": "home", "storage": "home",
    "kitchen": "kitchen", "cookware": "kitchen", "bakeware": "kitchen",
    "sports": "fitness", "fitness": "fitness", "yoga": "fitness", "gym": "fitness",
    "pet": "pets", "dog": "pets", "cat": "pets",
    "automotive": "auto", "vehicle": "auto", "car": "auto",
    "toys": "toys", "baby": "toys", "children": "toys",
    "cosmetics": "cosmetics", "fragrance": "cosmetics",
}


def _map_category(raw_cat: str) -> str:
    lowered = raw_cat.lower().strip()
    for key, val in _CATEGORY_MAP.items():
        if key in lowered:
            return val
    return "other"


# ------------------------------------------------------------------ field mapping

def _map_live_item(item: Dict[str, Any], country: str) -> Dict[str, Any]:
    """Map a CJ /v1/product/list result to the scoring-field candidate shape.

    sellPrice = what CJ charges the dropshipper (supplier cost, confirmed 2026-07-05).
    retail_price = None — suggestSellPrice is not in the list endpoint.
    image_url = productImage (available in list endpoint).
    """
    weight_raw = item.get("productWeight") or item.get("weight")
    weight_kg = None
    if weight_raw is not None:
        try:
            weight_kg = round(float(weight_raw) / 1000, 3)
        except (ValueError, TypeError):
            pass

    cost_raw = item.get("sellPrice")
    supplier_cost = None
    if cost_raw is not None:
        try:
            supplier_cost = float(cost_raw)
        except (ValueError, TypeError):
            pass

    return {
        "name": (item.get("productNameEn") or item.get("name") or "").strip(),
        "category": _map_category(item.get("categoryName") or item.get("category") or ""),
        "country": country,
        "retail_price": None,           # suggestSellPrice not in list endpoint
        "supplier_cost": supplier_cost, # sellPrice = dropshipper cost (confirmed)
        "shipping_cost": None,          # requires separate CJ shipping API call
        "product_weight_kg": weight_kg,
        "source_url": None,             # productUrl not returned by CJ list API
        "image_url": item.get("productImage") or None,
        "item_id": str(item["pid"]) if item.get("pid") else None,
        # Social/trend signals not available from CJ
        "trends_interest": None,
        "trends_direction_pct": None,
        "amazon_bsr": None,
        "tiktok_hashtag_views": None,
        "tiktok_momentum": None,
        "meta_active_advertisers": None,
        "aliexpress_sellers_1k": None,
        "competitor_count": None,
        "diff_complement_skus": None,
        "alltime_current_value": None,
    }


# ------------------------------------------------------------------ stub data

_STUB_ITEMS: List[Dict[str, Any]] = [
    {
        "name": "Magnetic Phone Car Mount Holder",
        "category": "auto",
        "supplier_cost": 3.20,
        "retail_price": 14.99,
        "shipping_cost": 2.50,
        "product_weight_kg": 0.09,
        "source_url": None,
        "item_id": "stub-cj-001",
    },
    {
        "name": "Silicone Food Storage Bags Set 4pcs",
        "category": "kitchen",
        "supplier_cost": 2.80,
        "retail_price": 12.99,
        "shipping_cost": 2.20,
        "product_weight_kg": 0.18,
        "source_url": None,
        "item_id": "stub-cj-002",
    },
    {
        "name": "Posture Corrector Back Brace Adjustable",
        "category": "health",
        "supplier_cost": 4.50,
        "retail_price": 19.99,
        "shipping_cost": 3.00,
        "product_weight_kg": 0.20,
        "source_url": None,
        "item_id": "stub-cj-003",
    },
    {
        "name": "LED Night Light Plug-in Motion Sensor",
        "category": "home",
        "supplier_cost": 1.90,
        "retail_price": 8.99,
        "shipping_cost": 1.80,
        "product_weight_kg": 0.05,
        "source_url": None,
        "item_id": "stub-cj-004",
    },
    {
        "name": "Portable USB Rechargeable Blender",
        "category": "kitchen",
        "supplier_cost": 5.60,
        "retail_price": 22.99,
        "shipping_cost": 3.20,
        "product_weight_kg": 0.30,
        "source_url": None,
        "item_id": "stub-cj-005",
    },
]


def _stub_response(seeds: List[str], country: str) -> Dict[str, Any]:
    clean_seeds = [s for s in seeds if not _is_risky(s)]
    risky_seeds = [{"seed": s, "reason": "blocked keyword"} for s in seeds if _is_risky(s)]

    candidates: List[Dict[str, Any]] = []
    if clean_seeds:
        for item in _STUB_ITEMS:
            candidates.append({**item, "country": country})

    return {
        "candidates": candidates,
        "skipped": risky_seeds,
        "source": "cj_dropshipping_stub",
        "note": (
            "CJ_API_TOKEN not set — returning stub supplier data. "
            "Set CJ_API_TOKEN to enable live CJ Dropshipping catalog access."
        ),
    }


# ------------------------------------------------------------------ collector


class CjDropshippingCollector:
    """CJ Dropshipping API collector — stub or live depending on CJ_API_TOKEN."""

    _DEFAULT_BASE_URL = "https://developers.cjdropshipping.com/api2.0"

    def __init__(self) -> None:
        self.token: str = os.getenv("CJ_API_TOKEN", "")
        self.base_url: str = os.getenv("CJ_API_BASE_URL", self._DEFAULT_BASE_URL).rstrip("/")
        self.fallback_to_stub: bool = (
            os.getenv("CJ_FALLBACK_TO_STUB", "true").lower() in ("true", "1", "yes")
        )

    def _has_credentials(self) -> bool:
        return bool(self.token)

    def discover(
        self,
        seeds: List[str],
        country: str = "US",
        limit_per_seed: int = 5,
    ) -> Dict[str, Any]:
        if not self._has_credentials():
            return _stub_response(seeds, country)
        try:
            return self._live_discover(seeds, country, limit_per_seed)
        except Exception as exc:
            if self.fallback_to_stub:
                result = _stub_response(seeds, country)
                result["source"] = "cj_dropshipping_stub_fallback"
                result["note"] = (
                    f"CJ API error ({type(exc).__name__}: {exc}) — "
                    "fell back to stub data. "
                    "Set CJ_FALLBACK_TO_STUB=false to surface errors instead."
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

        with httpx.Client(timeout=15.0) as client:
            for seed in seeds:
                if _is_risky(seed):
                    skipped.append({"seed": seed, "reason": "blocked keyword"})
                    continue
                try:
                    resp = client.get(
                        f"{self.base_url}/v1/product/list",
                        headers={"CJ-Access-Token": self.token},
                        params={
                            "productNameEn": seed,
                            "pageNum": 1,
                            "pageSize": limit_per_seed,
                        },
                    )
                    resp.raise_for_status()
                    body = resp.json()
                    items = (
                        body.get("data", {}).get("list", [])
                        or body.get("data", [])
                        or []
                    )
                    for item in items:
                        title = item.get("productNameEn") or item.get("name") or ""
                        if _is_risky(title):
                            skipped.append({"seed": seed, "title": title, "reason": "blocked content"})
                            continue
                        candidates.append(_map_live_item(item, country))
                except Exception as exc:
                    skipped.append({"seed": seed, "reason": f"api_error: {exc}"})

        return {
            "candidates": candidates,
            "skipped": skipped,
            "source": "cj_dropshipping",
        }
