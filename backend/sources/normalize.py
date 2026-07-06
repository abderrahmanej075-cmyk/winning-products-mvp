"""Normalize any discovery candidate into the shared multi-source signal shape.

Fields are populated from whatever data is available in the candidate dict.
Missing fields are tracked in `missing_data` rather than silently omitted.
Signal fields use descriptive string values — never invented scores:
  strong / moderate / weak / favorable / saturated / unconfirmed / missing / negative
"""
from typing import Any, Dict, List, Optional

# Fields we track for data completeness; absent ones go into missing_data.
_SIGNAL_FIELDS: tuple = (
    "trends_interest", "trends_direction_pct", "seasonality_ratio",
    "amazon_bsr", "tiktok_hashtag_views", "tiktok_momentum",
    "meta_active_advertisers", "aliexpress_sellers_1k", "competitor_count",
    "diff_complement_skus", "alltime_current_value",
    "supplier_cost", "product_weight_kg", "shipping_cost",
)


def _demand_signal(p: dict) -> str:
    ti = p.get("trends_interest")
    bsr = p.get("amazon_bsr")
    if ti is None and bsr is None:
        return "missing"
    ti = ti or 0
    if ti >= 50 or (bsr is not None and bsr <= 5_000):
        return "strong"
    if ti >= 25 or (bsr is not None and bsr <= 50_000):
        return "moderate"
    return "weak"


def _trend_signal(p: dict) -> str:
    tdp = p.get("trends_direction_pct")
    mom = p.get("tiktok_momentum")
    if tdp is None and mom is None:
        return "missing"
    tdp = tdp or 0
    if tdp > 20 or mom == "surging":
        return "strong"
    if tdp > 0 or mom in ("rising", "stable"):
        return "moderate"
    return "weak"


def _competition_signal(p: dict) -> str:
    cc = p.get("competitor_count")
    al = p.get("aliexpress_sellers_1k")
    if cc is None and al is None:
        return "missing"
    cc = cc or 0
    al = al or 0
    if cc < 500 and al <= 3:
        return "favorable"
    if cc < 2_000 and al <= 10:
        return "moderate"
    return "saturated"


def _social_signal(p: dict) -> str:
    views = p.get("tiktok_hashtag_views")
    ads = p.get("meta_active_advertisers")
    if views is None and ads is None:
        return "missing"
    views = views or 0
    ads = ads or 0
    if views >= 10_000_000 or ads >= 5:
        return "strong"
    if views >= 1_000_000 or ads >= 1:
        return "moderate"
    return "weak"


def _supplier_signal(p: dict) -> str:
    cost = p.get("supplier_cost")
    price = p.get("retail_price")
    if cost is None:
        return "missing"
    if not price:
        return "unconfirmed"
    ratio = cost / price
    if ratio <= 0.30:
        return "strong"
    if ratio <= 0.50:
        return "moderate"
    return "weak"


def _margin_signal(p: dict) -> str:
    price = p.get("retail_price")
    cost = p.get("supplier_cost")
    ship = p.get("shipping_cost") or 0
    if price is None:
        return "missing"
    if cost is None:
        return "unconfirmed"
    net = price - cost - ship
    if net >= 15:
        return "strong"
    if net >= 8:
        return "moderate"
    if net >= 0:
        return "weak"
    return "negative"


def normalize_candidate(
    p: dict,
    *,
    source: str,
    query: str = "",
    score_result: Optional[Dict[str, Any]] = None,
) -> dict:
    """Map a scoring-field-named candidate dict to the shared multi-source signal shape.

    p            : candidate with scoring field names (retail_price, supplier_cost, …)
    source       : source identifier, e.g. "ebay" or "manual"
    query        : the search query or seed that produced this candidate
    score_result : output of scoring.score_product(p); scoring fields are empty when None
    """
    price = p.get("retail_price")
    cost = p.get("supplier_cost")
    ship = p.get("shipping_cost") or 0

    estimated_margin = (
        round(price - cost - ship, 2) if price is not None and cost is not None else None
    )

    missing_data = [f for f in _SIGNAL_FIELDS if p.get(f) is None]

    evidence: Dict[str, Any] = {
        k: p[k]
        for k in (
            "retail_price", "shipping_cost", "supplier_cost",
            "trends_interest", "amazon_bsr", "tiktok_hashtag_views",
            "tiktok_momentum", "meta_active_advertisers",
            "aliexpress_sellers_1k", "competitor_count",
        )
        if p.get(k) is not None
    }

    sr = score_result or {}
    return {
        "name": (p.get("name") or "").strip(),
        "category": p.get("category", "other"),
        "query": query,
        "source": source,
        "source_url": p.get("source_url"),
        "item_id": p.get("item_id"),
        "image_url": p.get("image_url"),
        "retail_price": price,
        "shipping_cost": ship or None,
        "supplier_cost": cost,
        "product_weight_kg": p.get("product_weight_kg"),
        "estimated_margin": estimated_margin,
        "score": sr.get("score"),
        "recommendation": sr.get("recommendation"),
        "positive_reasons": sr.get("positive_reasons", []),
        "caution_reasons": sr.get("caution_reasons", []),
        "filter_reasons": sr.get("filter_reasons", []),
        "demand_signal": _demand_signal(p),
        "trend_signal": _trend_signal(p),
        "competition_signal": _competition_signal(p),
        "social_signal": _social_signal(p),
        "supplier_signal": _supplier_signal(p),
        "margin_signal": _margin_signal(p),
        "risk_flags": sr.get("cautions", []),
        "missing_data": missing_data,
        "evidence": evidence,
    }
