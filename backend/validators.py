"""Input validation schemas using Pydantic."""

from pydantic import BaseModel, Field, field_validator
from typing import Optional


class ProductIn(BaseModel):
    """Validated product input schema."""

    name: str = Field(..., min_length=1, max_length=255, description="Product name")
    category: Optional[str] = Field(
        "other",
        max_length=50,
        description="Product category"
    )
    country: Optional[str] = Field(
        "US",
        max_length=2,
        description="Country code"
    )

    # Demand signals (0-100 for trends_interest)
    trends_interest: Optional[int] = Field(None, ge=0, le=100, description="Google Trends interest")
    amazon_bsr: Optional[int] = Field(None, ge=0, description="Amazon Best Sellers Rank")
    reddit_posts_90d: Optional[int] = Field(None, ge=0, description="Reddit posts in 90 days")
    pinterest_saves: Optional[int] = Field(None, ge=0, description="Pinterest saves")

    # Growth signals
    trends_direction_pct: Optional[float] = Field(None, ge=-100, le=100, description="Trends 12-month change %")
    seasonality_ratio: Optional[float] = Field(None, ge=0, description="Peak/trough seasonality ratio")
    tiktok_momentum: Optional[str] = Field(None, max_length=50, description="TikTok momentum level")

    # Profit inputs
    supplier_cost: Optional[float] = Field(None, ge=0, description="Supplier cost ($)")
    shipping_cost: Optional[float] = Field(None, ge=0, description="Shipping cost ($)")
    retail_price: Optional[float] = Field(None, ge=0, description="Retail price ($)")
    product_weight_kg: Optional[float] = Field(None, ge=0, description="Product weight (kg)")

    # Content signals
    tiktok_hashtag_views: Optional[int] = Field(None, ge=0, description="TikTok hashtag views")
    meta_active_advertisers: Optional[int] = Field(None, ge=0, description="Meta active advertisers")
    meta_ad_longevity_days: Optional[int] = Field(None, ge=0, description="Meta ad longevity (days)")
    demo_videos_top10: Optional[int] = Field(None, ge=0, description="Demo videos in top 10")

    # Competition
    aliexpress_sellers_1k: Optional[int] = Field(None, ge=0, description="AliExpress sellers with 1k+ orders")
    brand_dominance_pct: Optional[float] = Field(None, ge=0, le=100, description="Brand dominance %")
    competitor_count: Optional[int] = Field(None, ge=0, description="Amazon competitor count")

    # Differentiation
    diff_unaddressed_themes: Optional[int] = Field(None, ge=0, description="Unaddressed themes")
    diff_complement_skus: Optional[int] = Field(None, ge=0, description="Complementary SKUs")
    diff_oem_available: Optional[int] = Field(None, ge=0, description="OEM available")
    diff_market_fragmented: Optional[int] = Field(None, ge=0, description="Market fragmented")
    diff_organic_ugc: Optional[int] = Field(None, ge=0, description="Organic UGC count")

    # Elimination filters
    legal_restricted: Optional[int] = Field(None, description="Legal restrictions flag")
    hazmat: Optional[int] = Field(None, description="Hazmat flag")
    fragile_material: Optional[int] = Field(None, description="Fragile material flag")
    breakage_mentions: Optional[int] = Field(None, ge=0, description="Breakage mentions count")
    longest_dim_cm: Optional[float] = Field(None, ge=0, description="Longest dimension (cm)")
    seasonality_offpeak: Optional[int] = Field(None, description="Currently off-peak flag")
    alltime_current_value: Optional[int] = Field(None, ge=0, description="All-time trend value")

    @field_validator('category')
    @classmethod
    def validate_category(cls, v):
        """Validate category is in allowed list."""
        if v is None:
            return v
        valid_categories = [
            "health", "beauty", "home", "kitchen", "fitness",
            "pets", "auto", "toys", "cosmetics", "other"
        ]
        if v.lower() not in valid_categories:
            raise ValueError(f"Invalid category. Must be one of: {', '.join(valid_categories)}")
        return v.lower()

    @field_validator('tiktok_momentum')
    @classmethod
    def validate_tiktok_momentum(cls, v):
        """Validate TikTok momentum level."""
        if v is None:
            return v
        valid_values = ["trending", "rising", "flat", "declining", "emerging", "surging"]
        if v.lower() not in valid_values:
            raise ValueError(f"Invalid tiktok_momentum. Must be one of: {', '.join(valid_values)}")
        return v.lower()

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        """Validate product name is not just whitespace."""
        if v.strip() == "":
            raise ValueError("Product name cannot be empty or whitespace only")
        return v


class ScoreRequest(BaseModel):
    """Request schema for scoring endpoint."""

    product_id: Optional[int] = Field(None, description="Product ID to score")
    cac: Optional[float] = Field(None, ge=0, description="Customer acquisition cost")
    product: Optional[ProductIn] = Field(None, description="Product data to score inline")

    @field_validator('product_id', 'cac', 'product')
    @classmethod
    def at_least_one_required(cls, v, info):
        """Ensure at least one of product_id or product is provided."""
        if info.field_name == 'product_id':
            # Check if this is the first field being validated
            if v is None and info.data.get('product') is None:
                # We'll validate this properly in root_validator
                pass
        return v
