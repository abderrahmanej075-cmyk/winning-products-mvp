"""US market seed strategy for e-commerce product discovery.

Provides structured seed groups and specific eBay search query expansion
targeting the US dropshipping market. All seeds cover physical, lightweight,
profitable niches that avoid high-risk / restricted categories.
"""
from typing import Dict, List, Tuple

# ------------------------------------------------------------------ seed groups
# Each key is a recognizable seed label; each value is 4 specific eBay queries
# that produce tighter, more relevant results than the broad label alone.

SEED_GROUPS: Dict[str, List[str]] = {
    "home organization": [
        "under sink organizer plastic",
        "drawer organizer divider set",
        "closet storage shelf organizer",
        "cable management box cord organizer",
    ],
    "pet cleaning": [
        "self cleaning slicker brush dog",
        "cat hair remover roller reusable",
        "silicone pet grooming glove bath",
        "pet hair remover couch furniture",
    ],
    "car interior accessories": [
        "car seat back organizer kickproof",
        "car cup holder insert expander",
        "car trunk organizer collapsible",
        "car console organizer center",
    ],
    "kitchen storage": [
        "pantry organizer bins pull out",
        "refrigerator organizer drawer stackable",
        "pot lid organizer rack cabinet",
        "spice rack organizer cabinet door",
    ],
    "travel accessories": [
        "packing cubes luggage organizer set",
        "hanging travel toiletry bag",
        "RFID passport holder wallet slim",
        "memory foam travel neck pillow",
    ],
    "desk organization": [
        "desk cable clip organizer adhesive",
        "monitor stand riser storage drawer",
        "desk drawer organizer tray",
        "file document tray organizer desktop",
    ],
    "baby safety accessories": [
        "magnetic cabinet lock baby proofing",
        "baby corner guard furniture protector",
        "outlet cover plug baby proofing",
        "drawer latch lock baby safety",
    ],
    "bathroom organization": [
        "shower caddy tension pole no drilling",
        "over toilet shelf organizer bathroom",
        "towel bar adhesive no drill wall",
        "bathroom counter organizer tray",
    ],
    "closet organization": [
        "velvet non slip suit hangers",
        "shelf divider closet organizer",
        "hanging shoe organizer door pocket",
        "drawer divider bedroom adjustable",
    ],
    "reusable household items": [
        "reusable beeswax food wrap",
        "silicone stretch lid set reusable",
        "mesh produce bag reusable set",
        "cotton cloth napkin set reusable washable",
    ],
}

# ------------------------------------------------------------------ weak candidate filter

# Established brands we cannot dropship without authorization.
# Using a tuple for faster containment checks on long strings.
_WEAK_BRANDS: Tuple[str, ...] = (
    "apple", "samsung", "sony", "nike", "adidas", "dyson", "lego",
    "instant pot", "kitchenaid", "cuisinart", "vitamix", "breville",
    "fitbit", "garmin", "gopro", "bose", "jbl", "beats",
    "nintendo", "xbox", "playstation", "logitech", "canon", "nikon",
    "dell", "hp lenovo", "asus", "acer", "microsoft",
    "under armour", "reebok", "puma", "new balance", "the north face",
    "stanley", "yeti", "hydro flask",
)

# Title substrings that signal a weak, risky, or un-dropshippable listing.
# Dict maps substring → human-readable reason.
_WEAK_TITLE_TERMS: Dict[str, str] = {
    # Condition / second-hand
    "used ":            "second-hand item",
    "pre-owned":        "second-hand item",
    "refurbished":      "refurbished item",
    "vintage ":         "vintage/antique item",
    "antique ":         "vintage/antique item",
    "broken":           "damaged/for-parts listing",
    "for parts":        "for-parts listing",
    "as-is":            "as-is/damaged listing",
    "damaged":          "damaged item",
    "not working":      "damaged/for-parts listing",
    # Bulk / wholesale — single-unit dropshipping not viable
    "wholesale":        "wholesale/bulk listing",
    "lot of ":          "bulk lot listing",
    "pack of 100":      "bulk lot listing",
    "pack of 50":       "bulk lot listing",
    "case of 24":       "bulk lot listing",
    # High-return-risk electronics
    "motherboard":      "high-return-risk electronics",
    "graphics card":    "high-return-risk electronics",
    "processor":        "high-return-risk electronics",
    "circuit board":    "high-return-risk electronics",
    " gpu ":            "high-return-risk electronics",
    " cpu ":            "high-return-risk electronics",
    "power supply":     "high-return-risk electronics",
    # Fragile / breakage risk
    "crystal vase":     "fragile glass product",
    "glass vase":       "fragile glass product",
    "porcelain figurine": "fragile ceramic product",
    "ceramic mug set":  "fragile ceramic product",
    # Heavy / oversized
    "weight bench":     "heavy/oversized product",
    "barbell set":      "heavy/oversized product",
    "dumbbell set":     "heavy/oversized product",
    "kettlebell set":   "heavy/oversized product",
    # Generic spare parts — low differentiation
    "replacement filter": "generic replacement part",
    "spare part":       "generic replacement/spare part",
    "repair kit":       "generic repair kit",
}


def is_weak_candidate(title: str) -> Tuple[bool, str]:
    """Return (True, reason) when the title signals a weak/risky candidate.

    Runs after the risk filter in ebay.py so the two layers stay separate:
    - ebay.py: blocks unsafe/illegal content
    - seeds.py: filters low-quality/undropshippable listings
    """
    lowered = title.lower().strip()
    if not lowered or len(lowered) < 5:
        return True, "empty or invalid title"

    for brand in _WEAK_BRANDS:
        if brand in lowered:
            return True, f"branded product ({brand}) — authorization/copyright risk"

    for term, reason in _WEAK_TITLE_TERMS.items():
        if term in lowered:
            return True, reason

    return False, ""


# ------------------------------------------------------------------ seed expansion

def expand_seeds(seeds: List[str]) -> List[str]:
    """Expand recognized seed group names into their specific search queries.

    Seeds that do not match a known group name are passed through unchanged,
    so the function is always backward-compatible with free-text seeds.

    Example:
        expand_seeds(["home organization", "yoga mat"])
        → ["under sink organizer plastic",
           "drawer organizer divider set",
           "closet storage shelf organizer",
           "cable management box cord organizer",
           "yoga mat"]
    """
    expanded: List[str] = []
    for seed in seeds:
        key = seed.strip().lower()
        if key in SEED_GROUPS:
            expanded.extend(SEED_GROUPS[key])
        else:
            expanded.append(seed)
    return expanded
