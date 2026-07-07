"""Unit tests for backend/decision_engine.py

Run from the backend/ directory:
    python -m unittest test_decision_engine
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import decision_engine


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

REQUIRED_KEYS = frozenset({
    "decision",
    "decision_confidence",
    "margin_status",
    "estimated_net_margin",
    "missing_data",
    "risk_flags",
    "decision_reasons",
    "next_action",
})

# A fully-enriched product that satisfies every TEST condition.
# Override individual fields with _p() to create targeted test cases.
_COMPLETE = {
    "eliminated": False,
    "filter_reasons": [],
    "caution_reasons": [],
    "positive_reasons": ["strong demand", "trend signal"],
    "retail_price": 40.0,
    "supplier_cost": 10.0,
    "shipping_cost": 5.0,
    "net_profit_per_order": 5.0,  # 40 - 10 - 5 - 20 (CAC) = 5
    "confidence": "Medium",
    "recommendation": "Test with small budget",
    "image_url": "https://img.example.com/product.jpg",
    "product_weight_kg": 0.3,
    "source": "ebay",
    "item_id": "ebay-999",
    "score": 38.0,
    "score_max": 60,
    "score_breakdown": {},
    "shortlisted": False,
    "review_status": "new",
}


def _p(**kwargs):
    """Return a copy of _COMPLETE with overridden fields."""
    result = dict(_COMPLETE)
    result.update(kwargs)
    return result


# ---------------------------------------------------------------------------
# Output shape
# ---------------------------------------------------------------------------

class TestOutputShape(unittest.TestCase):

    def test_output_has_exactly_required_keys_on_complete_product(self):
        r = decision_engine.decide_product(_COMPLETE)
        self.assertEqual(set(r.keys()), REQUIRED_KEYS)

    def test_output_has_exactly_required_keys_on_empty_product(self):
        r = decision_engine.decide_product({})
        self.assertEqual(set(r.keys()), REQUIRED_KEYS)

    def test_decision_is_always_a_valid_value(self):
        for product in [
            _COMPLETE,
            _p(confidence="Low"),
            _p(retail_price=None, net_profit_per_order=None),
            {},
        ]:
            r = decision_engine.decide_product(product)
            self.assertIn(
                r["decision"],
                {"TEST", "WATCH", "NEEDS_ENRICHMENT", "REJECT"},
                msg=f"Unexpected decision for product {product}",
            )

    def test_decision_confidence_is_always_uppercase(self):
        for product in [_COMPLETE, _p(confidence="Low"), {}]:
            r = decision_engine.decide_product(product)
            self.assertIn(r["decision_confidence"], {"HIGH", "MEDIUM", "LOW"})

    def test_missing_data_is_always_a_list(self):
        for product in [_COMPLETE, {}]:
            r = decision_engine.decide_product(product)
            self.assertIsInstance(r["missing_data"], list)

    def test_risk_flags_is_always_a_list(self):
        for product in [_COMPLETE, {}]:
            r = decision_engine.decide_product(product)
            self.assertIsInstance(r["risk_flags"], list)

    def test_decision_reasons_is_always_a_list(self):
        for product in [_COMPLETE, {}]:
            r = decision_engine.decide_product(product)
            self.assertIsInstance(r["decision_reasons"], list)


# ---------------------------------------------------------------------------
# REJECT rules
# ---------------------------------------------------------------------------

class TestReject(unittest.TestCase):

    def test_negative_net_profit_gives_reject(self):
        r = decision_engine.decide_product(_p(net_profit_per_order=-1.0))
        self.assertEqual(r["decision"], "REJECT")
        self.assertEqual(r["next_action"], "reject_product")

    def test_eliminated_true_gives_reject(self):
        r = decision_engine.decide_product(_p(
            eliminated=True,
            filter_reasons=["F7 digital: intangible product"],
        ))
        self.assertEqual(r["decision"], "REJECT")
        self.assertEqual(r["next_action"], "reject_product")

    def test_filter_reasons_non_empty_gives_reject(self):
        r = decision_engine.decide_product(_p(
            eliminated=False,
            filter_reasons=["F1 legal: restricted category"],
        ))
        self.assertEqual(r["decision"], "REJECT")
        self.assertEqual(r["next_action"], "reject_product")

    def test_filter_reasons_are_passed_through_as_decision_reasons(self):
        reasons_in = ["F1 legal: restricted category"]
        r = decision_engine.decide_product(_p(
            eliminated=True,
            filter_reasons=reasons_in,
        ))
        self.assertEqual(r["decision_reasons"], reasons_in)

    def test_supplier_cost_equal_to_retail_gives_reject(self):
        # net_profit is None so the negative-net check does not fire first
        r = decision_engine.decide_product(_p(
            supplier_cost=40.0,
            retail_price=40.0,
            net_profit_per_order=None,
        ))
        self.assertEqual(r["decision"], "REJECT")

    def test_supplier_cost_greater_than_retail_gives_reject(self):
        r = decision_engine.decide_product(_p(
            supplier_cost=50.0,
            retail_price=40.0,
            net_profit_per_order=None,
        ))
        self.assertEqual(r["decision"], "REJECT")

    def test_missing_supplier_cost_on_cj_gives_reject(self):
        r = decision_engine.decide_product(_p(
            supplier_cost=None,
            source="cj_dropshipping",
            net_profit_per_order=None,
        ))
        self.assertEqual(r["decision"], "REJECT")
        self.assertEqual(r["next_action"], "reject_product")


# ---------------------------------------------------------------------------
# NEEDS_ENRICHMENT rules
# ---------------------------------------------------------------------------

class TestNeedsEnrichment(unittest.TestCase):

    def test_missing_retail_price_gives_needs_enrichment(self):
        r = decision_engine.decide_product(_p(
            retail_price=None,
            net_profit_per_order=None,
        ))
        self.assertEqual(r["decision"], "NEEDS_ENRICHMENT")
        self.assertEqual(r["next_action"], "run_ebay_benchmark")
        self.assertIn("retail_price", r["missing_data"])

    def test_missing_supplier_cost_non_cj_gives_needs_enrichment(self):
        r = decision_engine.decide_product(_p(
            supplier_cost=None,
            source="ebay",
            net_profit_per_order=None,
        ))
        self.assertEqual(r["decision"], "NEEDS_ENRICHMENT")
        self.assertEqual(r["next_action"], "operator_review_required")
        self.assertIn("supplier_cost", r["missing_data"])

    def test_missing_shipping_cost_with_item_id_gives_cj_enrichment(self):
        r = decision_engine.decide_product(_p(
            shipping_cost=None,
            net_profit_per_order=None,
            source="cj_dropshipping",
            item_id="cj_pid_abc",
        ))
        self.assertEqual(r["decision"], "NEEDS_ENRICHMENT")
        self.assertEqual(r["next_action"], "run_cj_shipping_enrichment")
        self.assertIn("shipping_cost", r["missing_data"])

    def test_missing_shipping_cost_without_item_id_gives_operator_review(self):
        r = decision_engine.decide_product(_p(
            shipping_cost=None,
            net_profit_per_order=None,
            item_id=None,
        ))
        self.assertEqual(r["decision"], "NEEDS_ENRICHMENT")
        self.assertEqual(r["next_action"], "operator_review_required")

    def test_ebay_product_with_item_id_missing_shipping_gives_operator_review_not_cj(self):
        # eBay products have item_id but must NOT trigger CJ shipping enrichment.
        r = decision_engine.decide_product(_p(
            shipping_cost=None,
            net_profit_per_order=None,
            source="ebay",
            item_id="ebay-123",
        ))
        self.assertEqual(r["decision"], "NEEDS_ENRICHMENT")
        self.assertEqual(r["next_action"], "operator_review_required")
        self.assertNotEqual(r["next_action"], "run_cj_shipping_enrichment")

    def test_missing_image_url_gives_needs_enrichment(self):
        r = decision_engine.decide_product(_p(image_url=None))
        self.assertEqual(r["decision"], "NEEDS_ENRICHMENT")
        self.assertEqual(r["next_action"], "operator_review_required")
        self.assertIn("image_url", r["missing_data"])

    def test_missing_weight_on_cj_gives_needs_enrichment(self):
        r = decision_engine.decide_product(_p(
            product_weight_kg=None,
            source="cj_dropshipping",
        ))
        self.assertEqual(r["decision"], "NEEDS_ENRICHMENT")
        self.assertEqual(r["next_action"], "run_cj_detail_enrichment")
        self.assertIn("product_weight_kg", r["missing_data"])

    def test_missing_weight_on_non_cj_does_not_block(self):
        # Non-CJ products: weight absence is not a NEEDS_ENRICHMENT trigger
        r = decision_engine.decide_product(_p(
            product_weight_kg=None,
            source="ebay",
        ))
        self.assertNotIn("product_weight_kg", r["missing_data"])
        # Product still passes through to TEST (all other conditions met)
        self.assertEqual(r["decision"], "TEST")


# ---------------------------------------------------------------------------
# TEST rules
# ---------------------------------------------------------------------------

class TestTest(unittest.TestCase):

    def test_complete_positive_product_gives_test(self):
        r = decision_engine.decide_product(_COMPLETE)
        self.assertEqual(r["decision"], "TEST")
        self.assertEqual(r["next_action"], "prepare_test_offer")
        self.assertEqual(r["missing_data"], [])

    def test_shipping_cost_zero_is_not_treated_as_missing(self):
        r = decision_engine.decide_product(_p(
            shipping_cost=0.0,
            net_profit_per_order=10.0,
        ))
        self.assertEqual(r["decision"], "TEST")
        self.assertNotIn("shipping_cost", r["missing_data"])

    def test_strong_candidate_recommendation_gives_test(self):
        r = decision_engine.decide_product(_p(
            recommendation="Strong candidate",
            confidence="High",
        ))
        self.assertEqual(r["decision"], "TEST")

    def test_zero_net_profit_cannot_be_test(self):
        # net_profit > 0 is required; exactly 0.0 is not > 0
        r = decision_engine.decide_product(_p(net_profit_per_order=0.0))
        self.assertNotEqual(r["decision"], "TEST")


# ---------------------------------------------------------------------------
# WATCH rules
# ---------------------------------------------------------------------------

class TestWatch(unittest.TestCase):

    def test_low_confidence_gives_watch_not_test(self):
        r = decision_engine.decide_product(_p(confidence="Low"))
        self.assertEqual(r["decision"], "WATCH")

    def test_watchlist_recommendation_gives_watch(self):
        r = decision_engine.decide_product(_p(
            recommendation="Watchlist",
            confidence="Low",
        ))
        self.assertEqual(r["decision"], "WATCH")

    def test_non_empty_caution_reasons_prevent_test(self):
        r = decision_engine.decide_product(_p(
            caution_reasons=["C1 margin caution: high competition"],
        ))
        self.assertEqual(r["decision"], "WATCH")

    def test_no_positive_reasons_prevents_test(self):
        r = decision_engine.decide_product(_p(positive_reasons=[]))
        self.assertEqual(r["decision"], "WATCH")

    def test_watch_decision_reasons_explain_test_failure(self):
        r = decision_engine.decide_product(_p(confidence="Low"))
        self.assertTrue(len(r["decision_reasons"]) > 0)
        self.assertTrue(any("Confidence" in reason or "confidence" in reason
                            for reason in r["decision_reasons"]))


# ---------------------------------------------------------------------------
# risk_flags derivation
# ---------------------------------------------------------------------------

class TestRiskFlags(unittest.TestCase):

    def test_legal_filter_reason_produces_legal_risk(self):
        r = decision_engine.decide_product(_p(
            eliminated=True,
            filter_reasons=["F1 legal: restricted product class"],
        ))
        self.assertIn("restricted_or_legal_risk", r["risk_flags"])

    def test_hazmat_reason_produces_hazmat_risk(self):
        r = decision_engine.decide_product(_p(
            eliminated=True,
            filter_reasons=["F2 shipping: hazmat"],
        ))
        self.assertIn("hazmat_or_battery_risk", r["risk_flags"])
        self.assertIn("shipping_risk", r["risk_flags"])

    def test_fragile_reason_produces_fragile_risk(self):
        r = decision_engine.decide_product(_p(
            eliminated=True,
            filter_reasons=["F3 fragility: breakage reports"],
        ))
        self.assertIn("fragile_risk", r["risk_flags"])

    def test_caution_reasons_produce_caution_risk(self):
        r = decision_engine.decide_product(_p(
            caution_reasons=["C1 brand caution: possible counterfeit"],
            confidence="Low",
        ))
        self.assertIn("caution_risk", r["risk_flags"])

    def test_risk_flags_are_deduplicated(self):
        r = decision_engine.decide_product(_p(
            eliminated=True,
            filter_reasons=["F1 legal: reason A", "F1 legal: reason B"],
        ))
        self.assertEqual(len(r["risk_flags"]), len(set(r["risk_flags"])))

    def test_risk_flags_are_sorted(self):
        r = decision_engine.decide_product(_p(
            eliminated=True,
            filter_reasons=["F1 legal: restricted", "F3 fragility: glass"],
        ))
        self.assertEqual(r["risk_flags"], sorted(r["risk_flags"]))

    def test_clean_product_has_no_risk_flags(self):
        r = decision_engine.decide_product(_COMPLETE)
        self.assertEqual(r["risk_flags"], [])

    def test_risk_flags_not_from_direct_input_keys(self):
        # Confirm engine does NOT read product["battery_risk"] or similar named keys.
        # Pass a product with such keys set; they must not affect output.
        r = decision_engine.decide_product(_p(
            battery_risk="yes",
            fragile_risk=True,
            restricted_category_risk="high",
        ))
        # Clean product passes -> TEST, risk_flags empty (keys above are ignored)
        self.assertEqual(r["decision"], "TEST")
        self.assertEqual(r["risk_flags"], [])


# ---------------------------------------------------------------------------
# decision_confidence
# ---------------------------------------------------------------------------

class TestDecisionConfidence(unittest.TestCase):

    def test_high_when_all_fields_present_and_medium_scoring_confidence(self):
        r = decision_engine.decide_product(_COMPLETE)
        # All fields + confidence="Medium" + no filter_reasons -> HIGH
        self.assertEqual(r["decision_confidence"], "HIGH")

    def test_high_when_scoring_confidence_is_high(self):
        r = decision_engine.decide_product(_p(confidence="High"))
        self.assertEqual(r["decision_confidence"], "HIGH")

    def test_medium_when_shipping_missing(self):
        r = decision_engine.decide_product(_p(
            shipping_cost=None,
            net_profit_per_order=None,
        ))
        # retail_price and supplier_cost present, no filter_reasons -> MEDIUM
        self.assertEqual(r["decision_confidence"], "MEDIUM")

    def test_low_when_retail_missing(self):
        r = decision_engine.decide_product(_p(
            retail_price=None,
            net_profit_per_order=None,
        ))
        self.assertEqual(r["decision_confidence"], "LOW")

    def test_low_when_filter_reasons_present(self):
        r = decision_engine.decide_product(_p(
            eliminated=True,
            filter_reasons=["F1 legal: restricted"],
        ))
        self.assertEqual(r["decision_confidence"], "LOW")


# ---------------------------------------------------------------------------
# margin_status
# ---------------------------------------------------------------------------

class TestMarginStatus(unittest.TestCase):

    def test_strong_margin_at_35_percent(self):
        r = decision_engine.decide_product(_p(
            retail_price=100.0,
            net_profit_per_order=35.0,
        ))
        self.assertEqual(r["margin_status"], "strong_margin")
        self.assertEqual(r["estimated_net_margin"], 35.0)

    def test_acceptable_margin_at_20_percent(self):
        r = decision_engine.decide_product(_p(
            retail_price=100.0,
            net_profit_per_order=20.0,
        ))
        self.assertEqual(r["margin_status"], "acceptable_margin")

    def test_weak_margin_below_20_percent(self):
        r = decision_engine.decide_product(_p(
            retail_price=100.0,
            net_profit_per_order=10.0,
        ))
        self.assertEqual(r["margin_status"], "weak_margin")

    def test_weak_margin_at_very_small_positive(self):
        r = decision_engine.decide_product(_p(
            retail_price=100.0,
            net_profit_per_order=1.0,
        ))
        self.assertEqual(r["margin_status"], "weak_margin")

    def test_negative_margin(self):
        r = decision_engine.decide_product(_p(net_profit_per_order=-5.0))
        self.assertEqual(r["margin_status"], "negative_margin")
        self.assertEqual(r["decision"], "REJECT")

    def test_unknown_margin_when_net_is_none(self):
        r = decision_engine.decide_product(_p(
            shipping_cost=None,
            net_profit_per_order=None,
        ))
        self.assertEqual(r["margin_status"], "unknown_margin")
        self.assertIsNone(r["estimated_net_margin"])

    def test_unknown_margin_when_retail_price_is_none(self):
        r = decision_engine.decide_product(_p(
            retail_price=None,
            net_profit_per_order=None,
        ))
        self.assertEqual(r["margin_status"], "unknown_margin")
        self.assertIsNone(r["estimated_net_margin"])


if __name__ == "__main__":
    unittest.main()
