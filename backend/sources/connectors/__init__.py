"""Source connector registry and readiness planner.

CONNECTORS maps each source name to its connector instance.
build_readiness_plan() generates the actionable next-steps plan shown in
/sources/connectors/health, /discovery/multisource, and /reports/daily.

Recommended connection order for a small-budget dropshipping MVP:
  1) google_trends   — official Google Trends API (alpha/gated); BigQuery alternative available
  2) reddit          — free tier, strong buyer pain-point signals
  3) youtube         — free quota, review-volume and demand signals
  4) amazon / keepa  — best BSR data; keepa is easier/cheaper to activate
  5) aliexpress / cj — supplier cost and seller count for margin validation
  6) tiktok / meta   — social proof signals; approval can take weeks
"""
from .base import BaseConnector
from .google_trends_official import GoogleTrendsOfficialConnector


# --------------------------------------------------------------------------- connector definitions


class EbayConnector(BaseConnector):
    name = "ebay"
    label = "eBay Browse API"
    implemented = True
    requires_credentials = True
    required_env_vars = ["EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"]
    signal_types_supported = ["demand", "competition", "supplier"]
    current_behavior = (
        "Live eBay Sandbox via Browse API OAuth. "
        "Falls back to stub data when credentials are absent."
    )
    notes = (
        "Uses OAuth client credentials flow (Basic auth base64). "
        "Set EBAY_ENV=production to switch to the live marketplace."
    )
    recommended_priority = 0  # already active — excluded from next_sources_to_connect


class ManualConnector(BaseConnector):
    name = "manual"
    label = "Manual Entry"
    implemented = True
    requires_credentials = False
    required_env_vars = []
    signal_types_supported = ["demand", "trend", "competition", "social", "supplier", "pain_point"]
    current_behavior = (
        "Manual product data submitted via /discovery/manual or "
        "the manual_candidates field in POST /discovery/multisource."
    )
    notes = (
        "Always active. Supports all signal types. "
        "Use for human-curated data, quick tests, or evidence injection."
    )
    recommended_priority = 0


class RedditConnector(BaseConnector):
    name = "reddit"
    label = "Reddit API (PRAW)"
    implemented = False
    requires_credentials = True
    required_env_vars = ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"]
    signal_types_supported = ["pain_point", "demand", "social"]
    current_behavior = (
        "Not connected yet. Will surface buyer pain points and demand signals "
        "from subreddit posts and comments."
    )
    notes = (
        "Free tier available. Register an app at reddit.com/prefs/apps "
        "to get REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET. Add praw to requirements.txt."
    )
    recommended_priority = 2


class YouTubeConnector(BaseConnector):
    name = "youtube"
    label = "YouTube Data API v3"
    implemented = False
    requires_credentials = True
    required_env_vars = ["YOUTUBE_API_KEY"]
    signal_types_supported = ["demand", "social", "trend"]
    current_behavior = (
        "Not connected yet. Will provide review video count and "
        "trending product signals from YouTube search."
    )
    notes = (
        "Free daily quota (10,000 units). Create an API key in Google Cloud Console "
        "under 'YouTube Data API v3'. Add google-api-python-client to requirements.txt."
    )
    recommended_priority = 3


class AmazonConnector(BaseConnector):
    name = "amazon"
    label = "Amazon Product Advertising API v5"
    implemented = False
    requires_credentials = True
    required_env_vars = [
        "AMAZON_PAAPI_ACCESS_KEY",
        "AMAZON_PAAPI_SECRET_KEY",
        "AMAZON_PAAPI_PARTNER_TAG",
    ]
    signal_types_supported = ["demand", "competition"]
    current_behavior = (
        "Not connected yet. Will provide Best Seller Rank (BSR), "
        "competitor count, and review volume."
    )
    notes = (
        "Requires an active Amazon Associates account with PA-API v5 access. "
        "Approval can take several weeks. Consider Keepa as a faster alternative. "
        "Add paapi5-python-sdk to requirements.txt when wiring."
    )
    recommended_priority = 4


class KeepaConnector(BaseConnector):
    name = "keepa"
    label = "Keepa API"
    implemented = False
    requires_credentials = True
    required_env_vars = ["KEEPA_API_KEY"]
    signal_types_supported = ["demand", "competition"]
    current_behavior = (
        "Not connected yet. Will provide Amazon BSR history and price tracking "
        "as a simpler alternative to the PA-API."
    )
    notes = (
        "Paid API (~$15/month). Easier to activate than Amazon PA-API. "
        "Good historical BSR coverage. Add keepa to requirements.txt."
    )
    recommended_priority = 4  # same priority tier as Amazon


class AliexpressConnector(BaseConnector):
    name = "aliexpress"
    label = "AliExpress Affiliate API"
    implemented = False
    requires_credentials = True
    required_env_vars = ["ALIEXPRESS_API_KEY"]
    signal_types_supported = ["supplier", "competition"]
    current_behavior = (
        "Not connected yet. Will provide AliExpress seller count and "
        "supplier cost estimates."
    )
    notes = (
        "Free affiliate API. Register at portals.aliexpress.com. "
        "Add iop-sdk-python to requirements.txt when wiring."
    )
    recommended_priority = 5


class CjConnector(BaseConnector):
    name = "cj_dropshipping"
    label = "CJ Dropshipping API"
    implemented = False
    requires_credentials = True
    required_env_vars = ["CJ_API_KEY"]
    signal_types_supported = ["supplier"]
    current_behavior = (
        "Not connected yet. Will provide supplier cost and lead time "
        "from CJ Dropshipping catalog."
    )
    notes = (
        "Free API key after account registration at cjdropshipping.com. "
        "Good alternative to AliExpress for supplier signal."
    )
    recommended_priority = 5


class TikTokConnector(BaseConnector):
    name = "tiktok"
    label = "TikTok Research API"
    implemented = False
    requires_credentials = True
    required_env_vars = ["TIKTOK_RESEARCH_API_KEY"]
    signal_types_supported = ["social", "trend"]
    current_behavior = (
        "Not connected yet. Will provide TikTok hashtag view counts "
        "and product momentum signals."
    )
    notes = (
        "Requires an approved TikTok Research API application. "
        "Approval can take 2–4 weeks. Apply at developers.tiktok.com."
    )
    recommended_priority = 6


class MetaConnector(BaseConnector):
    name = "meta"
    label = "Meta Marketing API"
    implemented = False
    requires_credentials = True
    required_env_vars = ["META_MARKETING_ACCESS_TOKEN"]
    signal_types_supported = ["social", "demand"]
    current_behavior = (
        "Not connected yet. Will provide Meta active advertiser count "
        "and ad longevity signals."
    )
    notes = (
        "Requires a Meta Business account and a Marketing API access token. "
        "Create a system user token in Meta Business Manager."
    )
    recommended_priority = 6


# --------------------------------------------------------------------------- registry

_CONNECTOR_INSTANCES: list = [
    EbayConnector(),
    ManualConnector(),
    GoogleTrendsOfficialConnector(),
    RedditConnector(),
    YouTubeConnector(),
    AmazonConnector(),
    KeepaConnector(),
    AliexpressConnector(),
    CjConnector(),
    TikTokConnector(),
    MetaConnector(),
]

CONNECTORS: dict = {c.name: c for c in _CONNECTOR_INSTANCES}

# Connectors sorted by recommended_priority (ascending), then name for stability.
# Priority-0 connectors (ebay, manual) are excluded — they are already active.
_PRIORITY_ORDERED: list = sorted(
    [c for c in _CONNECTOR_INSTANCES if c.recommended_priority > 0],
    key=lambda c: (c.recommended_priority, c.name),
)


def build_readiness_plan() -> dict:
    """Return a planner dict for /sources/connectors/health and report endpoints.

    sources_ready            — connectors currently returning real data
    sources_missing_credentials — implemented connectors waiting for env vars
    next_sources_to_connect  — not-yet-active connectors in recommended order
    recommended_connection_order — ordered list of source names to connect next
    """
    sources_ready = [name for name, c in CONNECTORS.items() if c.status == "active"]
    sources_missing_credentials = [
        name for name, c in CONNECTORS.items() if c.status == "missing_credentials"
    ]
    next_to_connect = [
        {
            "name": c.name,
            "label": c.label,
            "required_env_vars": c.required_env_vars,
            "notes": c.notes,
        }
        for c in _PRIORITY_ORDERED
        if c.status != "active"
    ]
    return {
        "sources_ready": sources_ready,
        "sources_missing_credentials": sources_missing_credentials,
        "next_sources_to_connect": next_to_connect,
        "recommended_connection_order": [c.name for c in _PRIORITY_ORDERED],
    }
