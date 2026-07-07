"""Product Decision Engine - Phase B

Pure function: decide_product(product: dict) -> dict

Input:  the dict returned by _summary(row) in main.py
Output: decision fields merged into the product response via _summary_with_decision()

No DB, no network, no side effects.
Safe default is NEEDS_ENRICHMENT. Never defaults to TEST.

Inputs used (all from FIELD_SCHEMA_REVIEW.md section 7 confirmed-available list):
  eliminated, filter_reasons, caution_reasons, positive_reasons,
  retail_price, supplier_cost, shipping_cost, image_url, product_weight_kg,
  net_profit_per_order, confidence, recommendation, source, item_id

Risk fields (restricted_category_risk, battery_risk, etc.) are NOT input keys.
They are derived from filter_reasons / caution_reasons and appear only in output risk_flags.
"""


def _add_flags_from_reason(r_lower, flags):
    if "f1" in r_lower or "legal" in r_lower:
        flags.add("restricted_or_legal_risk")
    if "hazmat" in r_lower:
        flags.add("hazmat_or_battery_risk")
    if "f2" in r_lower or "shipping" in r_lower:
        flags.add("shipping_risk")
    if "f3" in r_lower or "fragil" in r_lower or "breakage" in r_lower:
        flags.add("fragile_risk")
    if "seasonality" in r_lower or "off-peak" in r_lower:
        flags.add("seasonality_risk")
    if "fad" in r_lower:
        flags.add("fad_risk")
    if "margin" in r_lower:
        flags.add("margin_risk")


def _derive_risk_flags(filter_reasons, caution_reasons):
    flags = set()
    for r in (filter_reasons or []):
        _add_flags_from_reason(r.lower(), flags)
    for r in (caution_reasons or []):
        _add_flags_from_reason(r.lower(), flags)
        flags.add("caution_risk")
    return sorted(flags)


def _result(decision, decision_confidence, margin_status, estimated_net_margin,
            missing_data, risk_flags, decision_reasons, next_action):
    return {
        "decision": decision,
        "decision_confidence": decision_confidence,
        "margin_status": margin_status,
        "estimated_net_margin": estimated_net_margin,
        "missing_data": missing_data,
        "risk_flags": risk_flags,
        "decision_reasons": decision_reasons,
        "next_action": next_action,
    }


def decide_product(product: dict) -> dict:
    """Evaluate a _summary(row) dict and produce a decision output dict.

    Decision priority: REJECT > NEEDS_ENRICHMENT > TEST (all conditions) > WATCH.
    WATCH is the catch-all when critical fields are present but TEST conditions fail.
    """
    # --- inputs ---
    eliminated       = product.get("eliminated", False)
    filter_reasons   = product.get("filter_reasons") or []
    caution_reasons  = product.get("caution_reasons") or []
    positive_reasons = product.get("positive_reasons") or []
    retail_price     = product.get("retail_price")
    supplier_cost    = product.get("supplier_cost")
    shipping_cost    = product.get("shipping_cost")      # 0.0 is valid, None is missing
    image_url        = product.get("image_url")
    weight_kg        = product.get("product_weight_kg")
    net_profit       = product.get("net_profit_per_order")
    confidence       = product.get("confidence", "Low")  # "High"/"Medium"/"Low" from scoring
    recommendation   = product.get("recommendation", "")
    source           = product.get("source") or ""
    item_id          = product.get("item_id")

    # --- missing_data: decision-relevant absent fields ---
    missing_data = []
    if retail_price is None:
        missing_data.append("retail_price")
    if supplier_cost is None:
        missing_data.append("supplier_cost")
    if shipping_cost is None:
        missing_data.append("shipping_cost")
    if image_url is None:
        missing_data.append("image_url")
    if weight_kg is None and source == "cj_dropshipping":
        missing_data.append("product_weight_kg")

    # --- risk_flags: derived from scoring outputs only ---
    risk_flags = _derive_risk_flags(filter_reasons, caution_reasons)

    # --- margin_status + estimated_net_margin ---
    if net_profit is None or retail_price is None or retail_price <= 0:
        margin_status = "unknown_margin"
        estimated_net_margin = None
    elif net_profit < 0:
        margin_status = "negative_margin"
        estimated_net_margin = round(net_profit, 2)
    else:
        ratio = net_profit / retail_price
        if ratio >= 0.35:
            margin_status = "strong_margin"
        elif ratio >= 0.20:
            margin_status = "acceptable_margin"
        else:
            margin_status = "weak_margin"
        estimated_net_margin = round(net_profit, 2)

    # --- decision_confidence ---
    if (retail_price is not None and supplier_cost is not None
            and shipping_cost is not None and image_url is not None
            and confidence in ("High", "Medium") and not filter_reasons):
        decision_confidence = "HIGH"
    elif retail_price is not None and supplier_cost is not None and not filter_reasons:
        decision_confidence = "MEDIUM"
    else:
        decision_confidence = "LOW"

    # ------------------------------------------------------------------ A) REJECT
    if eliminated or filter_reasons:
        reasons = list(filter_reasons) if filter_reasons else ["Product eliminated by scoring filter"]
        return _result("REJECT", decision_confidence, margin_status,
                       estimated_net_margin, missing_data, risk_flags,
                       reasons, "reject_product")

    if net_profit is not None and net_profit < 0:
        return _result("REJECT", decision_confidence, margin_status,
                       estimated_net_margin, missing_data, risk_flags,
                       [f"Net profit is negative ({round(net_profit, 2)})"],
                       "reject_product")

    if supplier_cost is not None and retail_price is not None and supplier_cost >= retail_price:
        return _result("REJECT", decision_confidence, margin_status,
                       estimated_net_margin, missing_data, risk_flags,
                       [f"Supplier cost ({supplier_cost}) >= retail price ({retail_price})"],
                       "reject_product")

    if supplier_cost is None and source == "cj_dropshipping":
        return _result("REJECT", decision_confidence, margin_status,
                       estimated_net_margin, missing_data, risk_flags,
                       ["CJ product missing supplier cost (data error)"],
                       "reject_product")

    # -------------------------------------------------------- B) NEEDS_ENRICHMENT
    # Use `is None` - shipping_cost=0.0 is a valid confirmed cost, not missing.
    if retail_price is None:
        return _result("NEEDS_ENRICHMENT", decision_confidence, margin_status,
                       estimated_net_margin, missing_data, risk_flags,
                       ["Market price benchmark missing"],
                       "run_ebay_benchmark")

    if supplier_cost is None:
        return _result("NEEDS_ENRICHMENT", decision_confidence, margin_status,
                       estimated_net_margin, missing_data, risk_flags,
                       ["Supplier cost missing"],
                       "operator_review_required")

    if shipping_cost is None:
        if source == "cj_dropshipping" and item_id:
            next_action = "run_cj_shipping_enrichment"
        else:
            next_action = "operator_review_required"
        return _result("NEEDS_ENRICHMENT", decision_confidence, margin_status,
                       estimated_net_margin, missing_data, risk_flags,
                       ["Shipping cost missing"],
                       next_action)

    if image_url is None:
        return _result("NEEDS_ENRICHMENT", decision_confidence, margin_status,
                       estimated_net_margin, missing_data, risk_flags,
                       ["Product image missing"],
                       "operator_review_required")

    if weight_kg is None and source == "cj_dropshipping":
        return _result("NEEDS_ENRICHMENT", decision_confidence, margin_status,
                       estimated_net_margin, missing_data, risk_flags,
                       ["CJ product weight missing"],
                       "run_cj_detail_enrichment")

    # All critical fields are present from this point.
    # ----------------------------------- D) TEST - all conditions must be true
    test_blockers = []
    if confidence not in ("High", "Medium"):
        test_blockers.append(
            f"Confidence is {confidence} - more signal data required")
    if recommendation not in ("Strong candidate", "Test with small budget"):
        test_blockers.append(
            f"Score recommendation is '{recommendation}'")
    if caution_reasons:
        test_blockers.append(
            f"Active cautions: {'; '.join(caution_reasons[:2])}")
    if not positive_reasons:
        test_blockers.append("No positive demand signals found")
    if net_profit is None or net_profit <= 0:
        test_blockers.append(f"Net profit not positive ({net_profit})")
    if missing_data:
        test_blockers.append(f"Incomplete data: {', '.join(missing_data)}")

    if not test_blockers:
        reasons = [
            f"Positive signals: {', '.join(positive_reasons[:3])}",
            f"Net profit: {round(net_profit, 2)} ({margin_status})",
            f"Confidence: {confidence} / {recommendation}",
        ]
        return _result("TEST", decision_confidence, margin_status,
                       estimated_net_margin, missing_data, risk_flags,
                       reasons, "prepare_test_offer")

    # ---- C) WATCH - critical fields present but TEST conditions not all met ----
    watch_reasons = list(test_blockers)
    if positive_reasons:
        watch_reasons.append(
            f"Positive signals observed: {', '.join(positive_reasons[:2])}")
    return _result("WATCH", decision_confidence, margin_status,
                   estimated_net_margin, missing_data, risk_flags,
                   watch_reasons, "keep_watchlist")
