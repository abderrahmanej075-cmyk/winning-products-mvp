"""Unit tests for eBay metadata mapping fix (item_id + image_url).

Run from the backend/ directory:
    python -m unittest test_ebay_metadata_mapping -v

No API calls. No network. No .env. No DB.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

from sources.ebay import _ebay_item_to_raw, _normalize_candidate
from sources.normalize import normalize_candidate


# ---------------------------------------------------------------------------
# Sample eBay item dicts
# ---------------------------------------------------------------------------

_FULL_ITEM = {
    "itemId": "v1|158043884007|0",
    "title": "Adjustable Posture Corrector Back Brace",
    "itemWebUrl": "https://www.ebay.com/itm/158043884007?hash=abc123",
    "price": {"value": "24.99", "currency": "USD"},
    "image": {
        "imageUrl": "https://i.ebayimg.com/images/g/abc/s-l225.jpg"
    },
    "shippingOptions": [
        {"shippingCost": {"value": "3.50", "currency": "USD"}}
    ],
    "categories": [{"categoryName": "Health & Beauty"}],
}

_NO_IMAGE_ITEM = {
    "itemId": "v1|999000000001|0",
    "title": "Test Product No Image",
    "itemWebUrl": "https://www.ebay.com/itm/999000000001",
    "price": {"value": "19.99", "currency": "USD"},
    # "image" key absent entirely
}

_NO_ITEM_ID_ITEM = {
    "title": "Test Product No ItemId",
    "itemWebUrl": "https://www.ebay.com/itm/000000000000",
    "price": {"value": "9.99", "currency": "USD"},
    "image": {"imageUrl": "https://i.ebayimg.com/images/g/xyz/s-l225.jpg"},
    # "itemId" key absent
}

_IMAGE_NONE_ITEM = {
    "itemId": "v1|888000000002|0",
    "title": "Test Product Image Key Present But None",
    "itemWebUrl": "https://www.ebay.com/itm/888000000002",
    "price": {"value": "14.99", "currency": "USD"},
    "image": None,
}


# ---------------------------------------------------------------------------
# TestEbayItemToRaw
# ---------------------------------------------------------------------------

class TestEbayItemToRaw(unittest.TestCase):

    def setUp(self):
        self.raw = _ebay_item_to_raw(_FULL_ITEM, "US")

    def test_item_id_extracted(self):
        self.assertEqual(self.raw["item_id"], "v1|158043884007|0")

    def test_image_url_extracted(self):
        self.assertEqual(
            self.raw["image_url"],
            "https://i.ebayimg.com/images/g/abc/s-l225.jpg",
        )

    def test_item_url_still_set(self):
        self.assertEqual(
            self.raw["item_url"],
            "https://www.ebay.com/itm/158043884007?hash=abc123",
        )

    def test_price_extracted(self):
        self.assertAlmostEqual(self.raw["price"], 24.99)

    def test_shipping_cost_extracted(self):
        self.assertAlmostEqual(self.raw["shipping_cost"], 3.5)

    def test_supplier_cost_is_none(self):
        self.assertIsNone(self.raw["supplier_cost"])

    def test_missing_image_returns_none_no_crash(self):
        raw = _ebay_item_to_raw(_NO_IMAGE_ITEM, "US")
        self.assertIsNone(raw["image_url"])

    def test_missing_item_id_returns_none_no_crash(self):
        raw = _ebay_item_to_raw(_NO_ITEM_ID_ITEM, "US")
        self.assertIsNone(raw["item_id"])

    def test_image_key_none_returns_image_url_none_no_crash(self):
        raw = _ebay_item_to_raw(_IMAGE_NONE_ITEM, "US")
        self.assertIsNone(raw["image_url"])

    def test_item_id_present_in_raw_keys(self):
        self.assertIn("item_id", self.raw)

    def test_image_url_present_in_raw_keys(self):
        self.assertIn("image_url", self.raw)


# ---------------------------------------------------------------------------
# TestNormalizeCandidate (eBay _normalize_candidate pass-through)
# ---------------------------------------------------------------------------

class TestNormalizeCandidateEbay(unittest.TestCase):

    def setUp(self):
        raw = _ebay_item_to_raw(_FULL_ITEM, "US")
        self.candidate = _normalize_candidate(raw)

    def test_item_id_passes_through(self):
        self.assertEqual(self.candidate["item_id"], "v1|158043884007|0")

    def test_image_url_passes_through(self):
        self.assertEqual(
            self.candidate["image_url"],
            "https://i.ebayimg.com/images/g/abc/s-l225.jpg",
        )

    def test_source_url_mapped_from_item_url(self):
        self.assertEqual(
            self.candidate["source_url"],
            "https://www.ebay.com/itm/158043884007?hash=abc123",
        )

    def test_retail_price_mapped(self):
        self.assertAlmostEqual(self.candidate["retail_price"], 24.99)

    def test_supplier_cost_is_none(self):
        self.assertIsNone(self.candidate["supplier_cost"])

    def test_missing_image_item_id_none_no_crash(self):
        raw = _ebay_item_to_raw(_NO_IMAGE_ITEM, "US")
        candidate = _normalize_candidate(raw)
        self.assertIsNone(candidate["image_url"])
        self.assertEqual(candidate["item_id"], "v1|999000000001|0")

    def test_missing_item_id_none_no_crash(self):
        raw = _ebay_item_to_raw(_NO_ITEM_ID_ITEM, "US")
        candidate = _normalize_candidate(raw)
        self.assertIsNone(candidate["item_id"])
        self.assertEqual(
            candidate["image_url"],
            "https://i.ebayimg.com/images/g/xyz/s-l225.jpg",
        )

    def test_source_url_unchanged_when_item_url_present(self):
        raw = _ebay_item_to_raw(_NO_IMAGE_ITEM, "US")
        candidate = _normalize_candidate(raw)
        self.assertEqual(
            candidate["source_url"],
            "https://www.ebay.com/itm/999000000001",
        )


# ---------------------------------------------------------------------------
# TestEndToEndPipeline
# ---------------------------------------------------------------------------

class TestEndToEndPipeline(unittest.TestCase):
    """Full pipeline: _ebay_item_to_raw -> _normalize_candidate -> normalize_candidate."""

    def setUp(self):
        raw = _ebay_item_to_raw(_FULL_ITEM, "US")
        candidate = _normalize_candidate(raw)
        self.result = normalize_candidate(candidate, source="ebay", query="posture corrector")

    def test_item_id_survives_full_pipeline(self):
        self.assertEqual(self.result["item_id"], "v1|158043884007|0")

    def test_image_url_survives_full_pipeline(self):
        self.assertEqual(
            self.result["image_url"],
            "https://i.ebayimg.com/images/g/abc/s-l225.jpg",
        )

    def test_source_url_survives_full_pipeline(self):
        self.assertEqual(
            self.result["source_url"],
            "https://www.ebay.com/itm/158043884007?hash=abc123",
        )

    def test_source_is_ebay(self):
        self.assertEqual(self.result["source"], "ebay")

    def test_retail_price_survives_full_pipeline(self):
        self.assertAlmostEqual(self.result["retail_price"], 24.99)

    def test_supplier_cost_is_none_in_full_pipeline(self):
        self.assertIsNone(self.result["supplier_cost"])

    def test_shipping_cost_behavior_unchanged(self):
        self.assertAlmostEqual(self.result["shipping_cost"], 3.5)

    def test_no_image_full_pipeline_no_crash(self):
        raw = _ebay_item_to_raw(_NO_IMAGE_ITEM, "US")
        candidate = _normalize_candidate(raw)
        result = normalize_candidate(candidate, source="ebay", query="test")
        self.assertIsNone(result["image_url"])
        self.assertEqual(result["item_id"], "v1|999000000001|0")


if __name__ == "__main__":
    unittest.main()
