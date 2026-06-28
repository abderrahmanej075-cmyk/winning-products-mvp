"""Source registry for multi-source product discovery.

Each entry describes one data source: its status (active / placeholder),
what signal it contributes, and whether credentials are required.
Placeholder sources are registered so the API can report them honestly
instead of silently ignoring unknown source names.
"""
from typing import Any, Dict

REGISTRY: Dict[str, Dict[str, Any]] = {
    "ebay": {
        "name": "ebay",
        "status": "active",
        "signal": "marketplace listings, retail price, shipping cost",
        "requires_credentials": True,
        "notes": (
            "Uses eBay Browse API with OAuth client credentials. "
            "Falls back to stub data when EBAY_CLIENT_ID is absent."
        ),
    },
    "manual": {
        "name": "manual",
        "status": "active",
        "signal": "manually entered product data with full field support",
        "requires_credentials": False,
        "notes": (
            "Products submitted via /discovery/manual or the manual_candidates "
            "field in POST /discovery/multisource."
        ),
    },
    "google_trends_placeholder": {
        "name": "google_trends_placeholder",
        "status": "placeholder",
        "signal": "search trend interest, 12-month direction, seasonality ratio",
        "requires_credentials": False,
        "notes": "Not active yet. Will integrate with Google Trends API when enabled.",
    },
    "amazon_placeholder": {
        "name": "amazon_placeholder",
        "status": "placeholder",
        "signal": "Best Seller Rank (BSR), competitor count, review volume",
        "requires_credentials": True,
        "notes": "Not active yet. Will integrate with Amazon Product Advertising API when enabled.",
    },
    "social_placeholder": {
        "name": "social_placeholder",
        "status": "placeholder",
        "signal": "TikTok hashtag views, TikTok momentum, Meta active advertisers",
        "requires_credentials": True,
        "notes": (
            "Not active yet. Will integrate with TikTok Research API "
            "and Meta Marketing API when enabled."
        ),
    },
    "supplier_placeholder": {
        "name": "supplier_placeholder",
        "status": "placeholder",
        "signal": "supplier cost, AliExpress seller count, lead time",
        "requires_credentials": False,
        "notes": (
            "Not active yet. Will integrate with AliExpress or CJ Dropshipping API when enabled."
        ),
    },
}

ACTIVE_SOURCES: frozenset = frozenset(k for k, v in REGISTRY.items() if v["status"] == "active")
