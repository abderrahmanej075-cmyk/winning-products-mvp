"""Deterministic scoring engine — Scoring Specification V2 (total /60).

Pure functions. No DB, no network. Rules implemented:
- Six categories x 10 = 60.
- Competition is inverted (less competition -> more points).
- Profit uses absolute net profit per order = price - cost - shipping - CAC.
- Missing fields are 'Not Measured': they earn no points AND their max is removed
  from the score denominator, so missing data lowers confidence but never the score.
- Pre-scoring elimination filters F1-F6.
- Confidence = share of the 19 collected fields that carry real data.
- Confidence caps the verdict; risk overlay (filter CAUTIONs) caps at Watchlist.
"""

DEFAULT_CAC = 20.0

# The 19 collected, measurable fields that count toward confidence.
# (Derived net-profit, CAC, and judgment/assessment fields are excluded.)
CONFIDENCE_FIELDS = [
    "trends_interest", "amazon_bsr", "reddit_posts_90d", "pinterest_saves",
    "trends_direction_pct", "seasonality_ratio", "tiktok_momentum",
    "retail_price", "supplier_cost", "shipping_cost", "product_weight_kg",
    "tiktok_hashtag_views", "meta_active_advertisers", "meta_ad_longevity_days",
    "aliexpress_sellers_1k", "brand_dominance_pct", "competitor_count",
    "diff_complement_skus", "diff_oem_available",
]

VERDICT_ORDER = ["Reject", "Watchlist", "Test with small budget", "Strong candidate"]

# Intangible/non-shippable product detection (F7)
_DIGITAL_STOP_WORDS = frozenset({
    "ebook", "e-book", "pdf guide", "digital download", "downloadable",
    "software", "saas", "app subscription", "license key", "licence key",
    "online course", "video course", "printable", "template pack",
    "font pack", "plugin", "preset pack",
})
_DIGITAL_CATEGORIES = frozenset({"software", "digital", "service", "ebooks", "apps"})


# ----------------------------------------------------------------------------- helpers
def compute_net(p, cac):
    r, c, s = p.get("retail_price"), p.get("supplier_cost"), p.get("shipping_cost")
    if r is None or c is None or s is None:
        return None
    return round(float(r) - float(c) - float(s) - float(cac), 2)


def _add(details, key, value, maxpts, fn):
    """Append a scored field; return (earned, contributed_max). Missing -> (0, 0)."""
    if value is None:
        details.append({"field": key, "points": None, "max": maxpts, "measured": False})
        return 0.0, 0.0
    pts = float(fn(value))
    details.append({"field": key, "points": pts, "max": maxpts, "measured": True})
    return pts, float(maxpts)


# ----------------------------------------------------------------------------- categories
def _demand(p):
    d, e, m = [], 0.0, 0.0
    a, b = _add(d, "demand_trends_interest", p.get("trends_interest"), 4,
                lambda v: 4 if v >= 70 else 2.5 if v >= 40 else 1 if v >= 10 else 0); e += a; m += b
    a, b = _add(d, "demand_amazon", p.get("amazon_bsr"), 3,
                lambda v: 3 if v <= 5000 else 2 if v <= 50000 else 1 if v <= 150000 else 0); e += a; m += b
    a, b = _add(d, "demand_reddit_volume", p.get("reddit_posts_90d"), 2,
                lambda v: 2 if v >= 15 else 1 if v >= 3 else 0); e += a; m += b
    a, b = _add(d, "demand_pinterest", p.get("pinterest_saves"), 1,
                lambda v: 1 if v >= 1000 else 0.5 if v >= 1 else 0); e += a; m += b
    return e, m, d


def _growth(p):
    d, e, m = [], 0.0, 0.0
    a, b = _add(d, "growth_trends_direction", p.get("trends_direction_pct"), 5,
                lambda v: 5 if v >= 50 else 4 if v >= 10 else 2 if v >= -10 else 0); e += a; m += b
    sr, cur = p.get("seasonality_ratio"), p.get("trends_interest")
    if sr is None:
        d.append({"field": "growth_seasonality", "points": None, "max": 2, "measured": False})
    else:
        if sr < 1.5:
            pts = 2 if (cur is not None and cur >= 40) else 0  # evergreen needs an absolute level floor
        elif sr < 3.0:
            pts = 1
        else:
            pts = 0
        d.append({"field": "growth_seasonality", "points": float(pts), "max": 2, "measured": True})
        e += pts; m += 2
    a, b = _add(d, "growth_tiktok_momentum", p.get("tiktok_momentum"), 3,
                lambda v: 3 if v in ("trending", "surging") else 2 if v in ("rising", "emerging") else 0); e += a; m += b
    return e, m, d


def _profit(p, cac):
    d, e, m = [], 0.0, 0.0
    net = compute_net(p, cac)
    if net is None:
        d.append({"field": "profit_net_per_order", "points": None, "max": 7, "measured": False})
    else:
        pts = 7 if net >= 25 else 5 if net >= 15 else 3 if net >= 8 else 1 if net >= 3 else 0
        d.append({"field": "profit_net_per_order", "points": float(pts), "max": 7,
                  "measured": True, "value": net})
        e += pts; m += 7
    a, b = _add(d, "profit_shipping_weight", p.get("product_weight_kg"), 3,
                lambda v: 3 if v < 0.3 else 1.5 if v <= 1.0 else 0); e += a; m += b
    return e, m, d


def _content(p):
    d, e, m = [], 0.0, 0.0
    a, b = _add(d, "content_tiktok_presence", p.get("tiktok_hashtag_views"), 3,
                lambda v: 3 if v >= 50_000_000 else 1.5 if v >= 1_000_000 else 0); e += a; m += b
    a, b = _add(d, "content_meta_advertisers", p.get("meta_active_advertisers"), 2,
                lambda v: 2 if v >= 5 else 1 if v >= 1 else 0); e += a; m += b
    a, b = _add(d, "content_meta_longevity", p.get("meta_ad_longevity_days"), 2,
                lambda v: 2 if v >= 30 else 1 if v >= 7 else 0); e += a; m += b
    a, b = _add(d, "content_demonstrability", p.get("demo_videos_top10"), 3,
                lambda v: 3 if v >= 5 else 1.5 if v >= 2 else 0); e += a; m += b
    return e, m, d


def _competition(p):
    """Inverted: less competition -> higher score."""
    d, e, m = [], 0.0, 0.0
    a, b = _add(d, "comp_aliexpress_saturation", p.get("aliexpress_sellers_1k"), 4,
                lambda v: 4 if v <= 2 else 2 if v <= 8 else 0); e += a; m += b
    a, b = _add(d, "comp_brand_dominance", p.get("brand_dominance_pct"), 3,
                lambda v: 3 if v < 25 else 1.5 if v <= 50 else 0); e += a; m += b
    a, b = _add(d, "comp_competitor_count", p.get("competitor_count"), 3,
                lambda v: 3 if v < 1000 else 1.5 if v <= 10000 else 0); e += a; m += b
    return e, m, d


def _diff(p):
    d, e, m = [], 0.0, 0.0
    a, b = _add(d, "diff_angle_gaps", p.get("diff_unaddressed_themes"), 3,
                lambda v: 3 if v >= 2 else 1.5 if v >= 1 else 0); e += a; m += b
    a, b = _add(d, "diff_bundling", p.get("diff_complement_skus"), 2,
                lambda v: 2 if v >= 2 else 1 if v >= 1 else 0); e += a; m += b
    oem, bd = p.get("diff_oem_available"), p.get("brand_dominance_pct")
    fragmented = bool(p.get("diff_market_fragmented")) or (bd is not None and bd < 25)
    if oem is None:
        d.append({"field": "diff_branding", "points": None, "max": 2, "measured": False})
    else:
        co = bool(oem)
        pts = 2 if (co and fragmented) else 1 if (co or fragmented) else 0
        d.append({"field": "diff_branding", "points": float(pts), "max": 2, "measured": True})
        e += pts; m += 2
    a, b = _add(d, "diff_ugc", p.get("diff_organic_ugc"), 3,
                lambda v: 3 if v >= 5 else 1.5 if v >= 2 else 0); e += a; m += b
    return e, m, d


# ----------------------------------------------------------------------------- filters
def run_filters(p):
    reasons, cautions = [], []

    # F1 legal
    if p.get("legal_restricted"):
        reasons.append("F1 legal: restricted/prohibited class")
    if (p.get("category") or "").lower() == "cosmetics":
        cautions.append("F1: cosmetic — FDA labeling required")

    # F2 shipping complexity
    w, dim, haz = p.get("product_weight_kg"), p.get("longest_dim_cm"), p.get("hazmat")
    sc, rp = p.get("shipping_cost"), p.get("retail_price")
    if w is not None and w > 2.0:
        reasons.append("F2 shipping: weight > 2kg")
    if dim is not None and dim > 60:
        reasons.append("F2 shipping: longest dimension > 60cm")
    if haz:
        reasons.append("F2 shipping: hazmat (battery/liquid/aerosol/magnetic)")
    if sc is not None and rp not in (None, 0) and sc > 0.30 * rp:
        reasons.append("F2 shipping: ship cost > 30% of retail")
    elif w is not None and 1.0 < w <= 2.0:
        cautions.append("F2: weight 1-2kg")

    # F3 fragility
    if p.get("fragile_material") and (p.get("breakage_mentions") or 0) >= 5:
        reasons.append("F3 fragility: fragile material + breakage reports")
    elif p.get("fragile_material"):
        cautions.append("F3: fragile material")

    # F4 seasonality
    sr = p.get("seasonality_ratio")
    if sr is not None and sr >= 3.0 and p.get("seasonality_offpeak"):
        reasons.append("F4 seasonality: strongly seasonal and currently off-peak")
    elif sr is not None and sr >= 3.0:
        cautions.append("F4: seasonal")

    # F5 market fit (US)
    ti, bsr, ads = p.get("trends_interest"), p.get("amazon_bsr"), p.get("meta_active_advertisers")
    if (ti is not None and ti < 10) and (bsr is None) and (ads in (None, 0)):
        reasons.append("F5 market fit: no US demand signal")

    # F6 fad-collapse (all-time Trends view; V<=20 and negative slope)
    av, dirpct = p.get("alltime_current_value"), p.get("trends_direction_pct")
    if av is not None and av <= 20 and dirpct is not None and dirpct < 0:
        reasons.append("F6 fad-collapse: historical peak >= 5x current and declining")

    # F7: digital/intangible — cannot be fulfilled via dropshipping
    name_lower = (p.get("name") or "").lower()
    cat_lower = (p.get("category") or "").lower()
    if any(kw in name_lower for kw in _DIGITAL_STOP_WORDS) or cat_lower in _DIGITAL_CATEGORIES:
        reasons.append("F7 digital: intangible/non-shippable product")

    # F8: gross margin check (before CAC)
    r8, c8, s8 = p.get("retail_price"), p.get("supplier_cost"), p.get("shipping_cost")
    if r8 is not None and c8 is not None and s8 is not None:
        gross = float(r8) - float(c8) - float(s8)
        if gross < 0:
            reasons.append("F8 margin: negative gross margin (price < cost + shipping)")
        elif gross < 3.0:
            cautions.append("F8: very thin gross margin (< $3 before CAC)")

    # C1: high competition combined with weak demand
    c1_comp = p.get("competitor_count")
    c1_ti = p.get("trends_interest")
    if c1_comp is not None and c1_comp > 15000 and c1_ti is not None and c1_ti < 25:
        cautions.append("C1: high competition (>15k competitors) with weak demand (trends < 25)")

    return {"status": "ELIMINATE" if reasons else "PASS", "reasons": reasons, "cautions": cautions}


# ----------------------------------------------------------------------------- confidence + verdict
def _confidence(p):
    supported = sum(1 for k in CONFIDENCE_FIELDS if p.get(k) is not None)
    denom = len(CONFIDENCE_FIELDS)
    ratio = supported / denom
    level = "High" if ratio >= 0.8 else "Medium" if ratio >= 0.5 else "Low"
    return supported, denom, round(ratio * 100, 1), level


def _lower(a, b):
    return a if VERDICT_ORDER.index(a) <= VERDICT_ORDER.index(b) else b


def _recommend(total, level, cautions):
    base = ("Strong candidate" if total >= 49 else
            "Test with small budget" if total >= 40 else
            "Watchlist" if total >= 30 else "Reject")
    cap = ("Strong candidate" if level == "High" else
           "Test with small budget" if level == "Medium" else "Watchlist")
    verdict = _lower(base, cap)
    if cautions:
        verdict = _lower(verdict, "Watchlist")
    return base, verdict


# ----------------------------------------------------------------------------- positive reasons
def _positive_reasons(cats: dict, net) -> list:
    reasons = []
    demand_d = cats.get("demand", {}).get("display", 0)
    if demand_d >= 7.0:
        reasons.append("Strong consumer demand (Google Trends + Amazon BSR)")
    elif demand_d >= 5.0:
        reasons.append("Moderate demand signal")
    if cats.get("trend_growth", {}).get("display", 0) >= 7.0:
        reasons.append("Positive and growing trend trajectory")
    if cats.get("profit", {}).get("display", 0) >= 7.0:
        reasons.append("Healthy profit margin per order")
    if net is not None and net >= 15:
        reasons.append(f"Est. net profit ${net:.2f}/order after shipping + CAC")
    if cats.get("competition", {}).get("display", 0) >= 7.0:
        reasons.append("Low competition — favorable market entry window")
    if cats.get("content", {}).get("display", 0) >= 6.0:
        reasons.append("Strong social media and advertising presence")
    if cats.get("differentiation", {}).get("display", 0) >= 6.0:
        reasons.append("Clear differentiation and bundling potential")
    return reasons


# ----------------------------------------------------------------------------- entry point
def score_product(p, cac=DEFAULT_CAC):
    filt = run_filters(p)
    net = compute_net(p, cac)
    sup, denom, pct, level = _confidence(p)
    conf = {"level": level, "supported": sup, "denominator": denom, "percent": pct}

    if filt["status"] == "ELIMINATE":
        return {
            "eliminated": True,
            "filter_reasons": filt["reasons"],
            "cautions": filt["cautions"],
            "caution_reasons": filt["cautions"],
            "score": None, "score_max": 60, "categories": {},
            "score_breakdown": {},
            "positive_reasons": [],
            "confidence": conf,
            "net_profit_per_order": net, "cac_used": cac,
            "base_verdict": "Reject",
            "recommendation": "Reject",
            "recommendation_reason": "Eliminated pre-scoring: " + "; ".join(filt["reasons"]),
        }

    cats = {}
    total_e = total_m = 0.0
    pipeline = [("demand", _demand(p)), ("trend_growth", _growth(p)),
                ("profit", _profit(p, cac)), ("content", _content(p)),
                ("competition", _competition(p)), ("differentiation", _diff(p))]
    for name, (e, m, d) in pipeline:
        cats[name] = {"earned": round(e, 2), "measured_max": round(m, 2),
                      "display": round((e / m * 10) if m > 0 else 0, 1), "fields": d}
        total_e += e
        total_m += m

    total = round((total_e / total_m * 60) if total_m > 0 else 0, 1)
    base, verdict = _recommend(total, level, filt["cautions"])

    reason = f"Score {total}/60 -> base '{base}'. Confidence {level} ({sup}/{denom} fields)."
    if level != "High":
        reason += f" Capped by {level} confidence."
    if filt["cautions"]:
        reason += " Risk overlay (" + "; ".join(filt["cautions"]) + ") -> capped at Watchlist."

    return {
        "eliminated": False,
        "filter_reasons": [],
        "cautions": filt["cautions"],
        "caution_reasons": filt["cautions"],
        "score": total, "score_max": 60, "categories": cats,
        "score_breakdown": {
            cat: {"score": round(data["display"], 1), "max": 10}
            for cat, data in cats.items()
        },
        "positive_reasons": _positive_reasons(cats, net),
        "confidence": conf,
        "net_profit_per_order": net, "cac_used": cac,
        "base_verdict": base,
        "recommendation": verdict,
        "recommendation_reason": reason,
    }
