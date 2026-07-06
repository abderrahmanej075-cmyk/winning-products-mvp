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
import os

from .base import BaseConnector
from .ebay_official import EbayOfficialConnector
from .google_trends_official import GoogleTrendsOfficialConnector
from ..tiktok_ads import read_live_flag
from ..cj_dropshipping import read_live_flag as cj_read_live_flag


# --------------------------------------------------------------------------- connector definitions


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
    implemented = True
    requires_credentials = False  # stub works without credentials
    required_env_vars = ["CJ_API_TOKEN"]
    signal_types_supported = ["supplier"]
    current_behavior = (
        "Returns 5 curated stub products when CJ_API_TOKEN is absent. "
        "Set CJ_API_TOKEN (Access Token from CJ dashboard, 180-day expiry) for live access. "
        "NOTE: sellPrice from /v1/product/list is the dropshipper cost (supplier_cost). "
        "retail_price is None in live mode — suggestSellPrice is not in the list endpoint."
    )
    notes = (
        "Official endpoint: GET /v1/product/list  (auth: CJ-Access-Token header). "
        "Register at cjdropshipping.com, generate an API Key, exchange it for an Access Token "
        "via POST /v1/authentication/getAccessToken. "
        "Access Token TTL: 180 days (per current CJ docs); Refresh Token TTL: 180 days. "
        "Refresh via POST /v1/authentication/refreshAccessToken before expiry. "
        "Status becomes 'active' only after POST /sources/cj_dropshipping/verify succeeds. "
        "CJ_FALLBACK_TO_STUB=true (default) returns stub data on API errors."
    )
    recommended_priority = 5

    _DEFAULT_BASE_URL = "https://developers.cjdropshipping.com/api2.0"

    def _cj_mode(self) -> str:
        """Return one of: stub_available | live_configured | live_untested | confirmed

        stub_available  — CJ_API_TOKEN absent → stub only
        live_configured — token set, verify not yet run
        live_untested   — verify ran but call failed or returned no candidates
        confirmed       — verify succeeded → status becomes 'active'
        """
        token = os.environ.get("CJ_API_TOKEN", "").strip()
        if not token:
            return "stub_available"
        flag = cj_read_live_flag()
        if flag is None:
            return "live_configured"
        if flag.get("live_call_confirmed"):
            return "confirmed"
        return "live_untested"

    @property
    def status(self) -> str:
        mode = self._cj_mode()
        return {
            "stub_available":   "stub_only",
            "live_configured":  "live_configured",
            "live_untested":    "live_untested",
            "confirmed":        "active",
        }.get(mode, "stub_only")

    def check(self) -> dict:
        base = super().check()
        mode = self._cj_mode()
        token_set = bool(os.environ.get("CJ_API_TOKEN", "").strip())
        base_url_set = bool(os.environ.get("CJ_API_BASE_URL", "").strip())
        flag = cj_read_live_flag()
        confirmed = bool(flag and flag.get("live_call_confirmed"))
        base_url_display = (
            os.environ.get("CJ_API_BASE_URL", "").strip() or self._DEFAULT_BASE_URL
        )
        base.update({
            "status": self.status,
            "can_fetch_real_data": confirmed,
            "cj_mode": mode,
            "token_configured": token_set,
            "base_url_configured": base_url_set,
            "endpoint_shape": (
                f"GET {base_url_display}/v1/product/list  "
                "(CJ-Access-Token header; params: productNameEn, pageNum, pageSize)"
            ),
            "live_call_confirmed": confirmed,
            "last_verified_at": flag.get("confirmed_at_utc") if flag else None,
            # Field availability — confirmed from live /v1/product/list response (2026-07-05)
            "supplier_cost_available": True,    # sellPrice = dropshipper cost (confirmed)
            "retail_price_available": False,    # suggestSellPrice not in list endpoint
            "image_url_available": True,        # productImage confirmed in list response
            "shipping_cost_available": False,   # requires POST /v1/logistic/freightCalculate
            "product_weight_available": True,   # productWeight (grams) confirmed in list response
            "source_url_available": False,      # productUrl not returned by CJ API
            "field_notes": (
                "sellPrice (list endpoint) = cost CJ charges the dropshipper = supplier_cost. "
                "retail_price is None — suggestSellPrice is in detail endpoint only. "
                "Margin scoring requires retail_price from external enrichment (eBay/manual)."
            ),
            "activation_note": (
                "Status becomes 'active' only after POST /sources/cj_dropshipping/verify succeeds. "
                "No manual promotion. Requires CJ_API_TOKEN (Access Token, 180-day TTL per current CJ docs)."
            ),
        })
        return base


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


class TikTokAdsConnector(BaseConnector):
    name = "tiktok_ads"
    label = "TikTok Ads Intelligence"
    implemented = True
    requires_credentials = False  # stub works without any credentials
    required_env_vars = ["TIKTOK_API_TOKEN"]
    signal_types_supported = ["demand", "social", "trend"]
    current_behavior = (
        "Status: pending_access — TikTok Commercial Content API access request submitted "
        "(org: Zaryotech, app: Zaryotech Product Discovery). "
        "Awaiting TikTok approval for research.adlib.basic scope. "
        "Stub data returned until access is granted and verified."
    )
    notes = (
        "Official path: TikTok Commercial Content API (POST /v2/research/adlib/ad/query/). "
        "Requires research.adlib.basic scope — not yet visible in TikTok Developer Portal. "
        "Support ticket submitted 2026-07-05. "
        "Set TIKTOK_API_PROVIDER=commercial_content_api while awaiting access. "
        "Status becomes 'active' only after POST /sources/tiktok_ads/verify succeeds."
    )
    recommended_priority = 1

    # Endpoint shape for each provider — included in health output for documentation
    _ENDPOINT_SHAPES = {
        "placeholder":            "N/A — no live product search endpoint on TikTok APIs. Stub only.",
        "commercial_content_api": "POST https://open.tiktokapis.com/v2/research/adlib/ad/query/  (Authorization: Bearer — requires research.adlib.basic scope — access pending)",
        "mock":                   "GET {TIKTOK_API_BASE_URL}/products/search  (user-controlled mock server)",
        "third_party":            "GET {TIKTOK_API_BASE_URL}/products/search  (provider-specific; check provider docs)",
    }

    def _tiktok_mode(self) -> str:
        """Return one of: stub_available | pending_access | missing_token | missing_base_url |
        live_configured | live_untested | confirmed

        stub_available   — provider=placeholder or unrecognised → stub only
        pending_access   — provider=commercial_content_api, awaiting TikTok API approval
        missing_token    — real provider set but TIKTOK_API_TOKEN absent
        missing_base_url — token set but TIKTOK_API_BASE_URL absent
        live_configured  — fully configured, POST /sources/tiktok_ads/verify not yet run
        live_untested    — verify was run but the live call failed or returned no candidates
        confirmed        — verify ran successfully → status becomes 'active'
        """
        provider = os.environ.get("TIKTOK_API_PROVIDER", "placeholder").strip().lower()
        token = os.environ.get("TIKTOK_API_TOKEN", "").strip()
        base_url = os.environ.get("TIKTOK_API_BASE_URL", "").strip()

        # commercial_content_api: official TikTok API — access request submitted,
        # awaiting TikTok approval. Treat as pending regardless of token state.
        if provider == "commercial_content_api":
            return "pending_access"

        if provider not in ("mock", "third_party"):
            return "stub_available"
        if not token:
            return "missing_token"
        if not base_url:
            return "missing_base_url"

        # Credentials are fully configured — check flag file for confirmation state.
        flag = read_live_flag()
        if flag is None:
            return "live_configured"   # never tested
        if flag.get("live_call_confirmed") and flag.get("provider") == provider:
            return "confirmed"         # live call succeeded for this provider
        return "live_untested"         # tested but call failed or provider changed

    @property
    def status(self) -> str:
        mode = self._tiktok_mode()
        return {
            "stub_available":   "stub_only",
            "pending_access":   "pending_access",
            "missing_token":    "stub_only",
            "missing_base_url": "stub_only",
            "live_configured":  "live_configured",
            "live_untested":    "live_untested",
            "confirmed":        "active",
        }.get(mode, "stub_only")

    def check(self) -> dict:
        base = super().check()
        provider = os.environ.get("TIKTOK_API_PROVIDER", "placeholder").strip().lower()
        token_set = bool(os.environ.get("TIKTOK_API_TOKEN", "").strip())
        base_url_set = bool(os.environ.get("TIKTOK_API_BASE_URL", "").strip())
        mode = self._tiktok_mode()
        flag = read_live_flag()
        confirmed = bool(flag and flag.get("live_call_confirmed") and flag.get("provider") == provider)
        endpoint_shape = self._ENDPOINT_SHAPES.get(provider, "unknown provider")

        update: dict = {
            "status": self.status,
            "can_fetch_real_data": confirmed,
            "tiktok_mode": mode,
            "provider": provider,
            "token_configured": token_set,
            "base_url_configured": base_url_set,
            "endpoint_shape": endpoint_shape,
            "live_call_confirmed": confirmed,
            "last_verified_at": flag.get("confirmed_at_utc") if flag else None,
            "activation_note": (
                "Status automatically becomes 'active' after POST /sources/tiktok_ads/verify "
                "succeeds. No manual promotion. "
                "Requires TIKTOK_API_PROVIDER=third_party|mock + TIKTOK_API_TOKEN + TIKTOK_API_BASE_URL."
            ),
        }

        if mode == "pending_access":
            update.update({
                "access_pending": True,
                "organization": "Zaryotech",
                "app_name": "Zaryotech Product Discovery",
                "requested_api": "TikTok Commercial Content API",
                "requested_scope": "research.adlib.basic",
                "endpoint_needed": "POST /v2/research/adlib/ad/query/",
                "blocker": (
                    "Commercial Content API product and research.adlib.basic scope "
                    "not visible in TikTok Developer Portal. Support ticket submitted 2026-07-05."
                ),
                "data_mode": "stub",
                "persisted": False,
                "activation_note": (
                    "Awaiting TikTok Commercial Content API access approval. "
                    "Status will be updated to live_configured once the API and scope "
                    "are visible in the portal and credentials are set."
                ),
            })

        base.update(update)
        return base


# --------------------------------------------------------------------------- registry

_CONNECTOR_INSTANCES: list = [
    EbayOfficialConnector(),
    ManualConnector(),
    TikTokAdsConnector(),
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
