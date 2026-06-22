"""Seed the local SQLite DB with 20 sample products.

IMPORTANT: these are ILLUSTRATIVE SAMPLE values to make the engine runnable today.
They are not live readings from Google Trends / Amazon / Meta / etc. When real
sources are connected, these fields fill from those sources instead.

Some products intentionally trip the elimination filters (fad, legal, fragility,
shipping) and a few leave fields blank to demonstrate the 'Not Measured' /
confidence behaviour.
"""
import os
from db import init_db, insert_product, DB_PATH
from logger import logger

PRODUCTS = [
    # 1 — strong-ish winner, fully measured (High confidence -> real verdict)
    dict(name="Posture Corrector Back Brace", category="health", country="US",
         trends_interest=55, amazon_bsr=3500, reddit_posts_90d=18, pinterest_saves=1500,
         trends_direction_pct=35, seasonality_ratio=1.4, tiktok_momentum="rising",
         supplier_cost=6, shipping_cost=3, retail_price=39, product_weight_kg=0.25,
         tiktok_hashtag_views=80_000_000, meta_active_advertisers=8, meta_ad_longevity_days=60,
         demo_videos_top10=7, aliexpress_sellers_1k=12, brand_dominance_pct=15, competitor_count=12000,
         diff_unaddressed_themes=2, diff_complement_skus=3, diff_oem_available=1,
         diff_market_fragmented=1, diff_organic_ugc=6, alltime_current_value=60),

    # 2 — commoditised; absolute-net lens + weak differentiation -> Reject
    dict(name="RGB LED Strip Lights", category="home", country="US",
         trends_interest=45, amazon_bsr=8000, reddit_posts_90d=6, pinterest_saves=2000,
         trends_direction_pct=5, seasonality_ratio=1.6, tiktok_momentum="flat",
         supplier_cost=4, shipping_cost=3, retail_price=14, product_weight_kg=0.2,
         tiktok_hashtag_views=120_000_000, meta_active_advertisers=10, meta_ad_longevity_days=20,
         demo_videos_top10=6, aliexpress_sellers_1k=30, brand_dominance_pct=18, competitor_count=25000,
         diff_unaddressed_themes=0, diff_complement_skus=1, diff_oem_available=1,
         diff_market_fragmented=1, diff_organic_ugc=2, alltime_current_value=50),

    # 3 — dead fad -> eliminated by F6
    dict(name="Fidget Spinner", category="toys", country="US",
         trends_interest=8, amazon_bsr=200000, trends_direction_pct=-30,
         supplier_cost=1, shipping_cost=2, retail_price=6, product_weight_kg=0.05,
         tiktok_hashtag_views=5_000_000, aliexpress_sellers_1k=40, brand_dominance_pct=10,
         competitor_count=40000, alltime_current_value=4),

    # 4 — cosmetic; scores well but F1 caution overlay caps at Watchlist
    dict(name="Argan Oil Hair Serum", category="cosmetics", country="US",
         trends_interest=40, amazon_bsr=12000, reddit_posts_90d=5, pinterest_saves=3000,
         trends_direction_pct=20, seasonality_ratio=1.3, tiktok_momentum="rising",
         supplier_cost=5, shipping_cost=3, retail_price=28, product_weight_kg=0.15,
         tiktok_hashtag_views=40_000_000, meta_active_advertisers=6, meta_ad_longevity_days=45,
         demo_videos_top10=4, aliexpress_sellers_1k=8, brand_dominance_pct=20, competitor_count=9000,
         diff_unaddressed_themes=2, diff_complement_skus=4, diff_oem_available=1,
         diff_market_fragmented=1, diff_organic_ugc=5, alltime_current_value=45),

    # 5 — portable blender
    dict(name="Portable Mini Blender", category="kitchen", country="US",
         trends_interest=50, amazon_bsr=4000, reddit_posts_90d=8, pinterest_saves=1200,
         trends_direction_pct=15, seasonality_ratio=1.8, tiktok_momentum="rising",
         supplier_cost=8, shipping_cost=4, retail_price=35, product_weight_kg=0.6,
         tiktok_hashtag_views=90_000_000, meta_active_advertisers=7, meta_ad_longevity_days=50,
         demo_videos_top10=6, aliexpress_sellers_1k=15, brand_dominance_pct=25, competitor_count=18000,
         diff_unaddressed_themes=1, diff_complement_skus=2, diff_oem_available=1,
         diff_market_fragmented=0, diff_organic_ugc=5, alltime_current_value=55),

    # 6 — low-ticket accessory; net negative -> Reject
    dict(name="Magnetic Phone Mount", category="auto", country="US",
         trends_interest=35, amazon_bsr=15000, reddit_posts_90d=4, pinterest_saves=300,
         trends_direction_pct=5, seasonality_ratio=1.2, tiktok_momentum="flat",
         supplier_cost=2.5, shipping_cost=2, retail_price=15, product_weight_kg=0.1,
         tiktok_hashtag_views=20_000_000, meta_active_advertisers=3, meta_ad_longevity_days=15,
         demo_videos_top10=3, aliexpress_sellers_1k=25, brand_dominance_pct=15, competitor_count=30000,
         diff_unaddressed_themes=0, diff_complement_skus=1, diff_oem_available=1,
         diff_market_fragmented=1, diff_organic_ugc=2, alltime_current_value=40),

    # 7 — partially measured (4 blanks) -> Medium confidence
    dict(name="Pet Hair Remover Roller", category="pets", country="US",
         trends_interest=38, amazon_bsr=9000,
         trends_direction_pct=12, seasonality_ratio=1.3, tiktok_momentum="rising",
         supplier_cost=3, shipping_cost=3, retail_price=22, product_weight_kg=0.2,
         tiktok_hashtag_views=35_000_000, meta_active_advertisers=5,
         demo_videos_top10=5, aliexpress_sellers_1k=10, brand_dominance_pct=20, competitor_count=11000,
         diff_unaddressed_themes=1, diff_complement_skus=2,
         diff_market_fragmented=0, diff_organic_ugc=4, alltime_current_value=42),

    # 8 — saturated, brand-dominated -> Reject
    dict(name="Insulated Water Bottle", category="fitness", country="US",
         trends_interest=42, amazon_bsr=6000, reddit_posts_90d=9, pinterest_saves=2500,
         trends_direction_pct=0, seasonality_ratio=2.5, tiktok_momentum="flat",
         supplier_cost=4, shipping_cost=5, retail_price=18, product_weight_kg=0.35,
         tiktok_hashtag_views=60_000_000, meta_active_advertisers=9, meta_ad_longevity_days=40,
         demo_videos_top10=2, aliexpress_sellers_1k=40, brand_dominance_pct=35, competitor_count=50000,
         diff_unaddressed_themes=0, diff_complement_skus=1, diff_oem_available=1,
         diff_market_fragmented=0, diff_organic_ugc=2, alltime_current_value=55),

    # 9 — blackhead vacuum
    dict(name="Blackhead Remover Vacuum", category="beauty", country="US",
         trends_interest=30, amazon_bsr=20000, reddit_posts_90d=6, pinterest_saves=600,
         trends_direction_pct=-5, seasonality_ratio=1.4, tiktok_momentum="flat",
         supplier_cost=5, shipping_cost=3, retail_price=25, product_weight_kg=0.2,
         tiktok_hashtag_views=25_000_000, meta_active_advertisers=4, meta_ad_longevity_days=20,
         demo_videos_top10=5, aliexpress_sellers_1k=18, brand_dominance_pct=15, competitor_count=22000,
         diff_unaddressed_themes=1, diff_complement_skus=2, diff_oem_available=1,
         diff_market_fragmented=1, diff_organic_ugc=3, alltime_current_value=50),

    # 10 — heated eyelash curler
    dict(name="Heated Eyelash Curler", category="beauty", country="US",
         trends_interest=28, amazon_bsr=25000, reddit_posts_90d=3, pinterest_saves=400,
         trends_direction_pct=8, seasonality_ratio=1.5, tiktok_momentum="rising",
         supplier_cost=4, shipping_cost=2, retail_price=19, product_weight_kg=0.1,
         tiktok_hashtag_views=30_000_000, meta_active_advertisers=3, meta_ad_longevity_days=15,
         demo_videos_top10=4, aliexpress_sellers_1k=12, brand_dominance_pct=18, competitor_count=14000,
         diff_unaddressed_themes=1, diff_complement_skus=1, diff_oem_available=1,
         diff_market_fragmented=1, diff_organic_ugc=3, alltime_current_value=40),

    # 11 — fragile -> eliminated by F3
    dict(name="Glass Coffee Mug Set", category="home", country="US",
         trends_interest=33, amazon_bsr=18000, supplier_cost=6, shipping_cost=6, retail_price=24,
         product_weight_kg=0.9, fragile_material=1, breakage_mentions=7,
         aliexpress_sellers_1k=20, brand_dominance_pct=22, competitor_count=20000,
         alltime_current_value=38),

    # 12 — legal -> eliminated by F1
    dict(name="Disposable Vape Pen", category="other", country="US",
         trends_interest=50, amazon_bsr=None, legal_restricted=1,
         supplier_cost=2, shipping_cost=2, retail_price=12, product_weight_kg=0.05),

    # 13 — past-peak decor item, declining but not collapsed -> Reject
    dict(name="Sunset Lamp Projector", category="home", country="US",
         trends_interest=35, amazon_bsr=18000, reddit_posts_90d=5, pinterest_saves=1800,
         trends_direction_pct=-15, seasonality_ratio=1.7, tiktok_momentum="flat",
         supplier_cost=4, shipping_cost=4, retail_price=20, product_weight_kg=0.4,
         tiktok_hashtag_views=70_000_000, meta_active_advertisers=5, meta_ad_longevity_days=25,
         demo_videos_top10=6, aliexpress_sellers_1k=22, brand_dominance_pct=20, competitor_count=20000,
         diff_unaddressed_themes=0, diff_complement_skus=1, diff_oem_available=1,
         diff_market_fragmented=1, diff_organic_ugc=3, alltime_current_value=30),

    # 14 — resistance bands
    dict(name="Resistance Bands Set", category="fitness", country="US",
         trends_interest=48, amazon_bsr=5000, reddit_posts_90d=10, pinterest_saves=1500,
         trends_direction_pct=10, seasonality_ratio=2.0, tiktok_momentum="rising",
         supplier_cost=4, shipping_cost=3, retail_price=25, product_weight_kg=0.3,
         tiktok_hashtag_views=50_000_000, meta_active_advertisers=6, meta_ad_longevity_days=35,
         demo_videos_top10=4, aliexpress_sellers_1k=20, brand_dominance_pct=22, competitor_count=28000,
         diff_unaddressed_themes=1, diff_complement_skus=3, diff_oem_available=1,
         diff_market_fragmented=1, diff_organic_ugc=4, alltime_current_value=50),

    # 15 — car vacuum
    dict(name="Handheld Car Vacuum", category="auto", country="US",
         trends_interest=33, amazon_bsr=12000, reddit_posts_90d=4, pinterest_saves=300,
         trends_direction_pct=3, seasonality_ratio=1.4, tiktok_momentum="flat",
         supplier_cost=9, shipping_cost=5, retail_price=30, product_weight_kg=0.8,
         tiktok_hashtag_views=20_000_000, meta_active_advertisers=4, meta_ad_longevity_days=20,
         demo_videos_top10=4, aliexpress_sellers_1k=16, brand_dominance_pct=18, competitor_count=16000,
         diff_unaddressed_themes=1, diff_complement_skus=2, diff_oem_available=1,
         diff_market_fragmented=1, diff_organic_ugc=2, alltime_current_value=38),

    # 16 — low-competition health niche -> Watchlist (near Test)
    dict(name="Cervical Neck Traction Device", category="health", country="US",
         trends_interest=30, amazon_bsr=14000, reddit_posts_90d=6, pinterest_saves=500,
         trends_direction_pct=18, seasonality_ratio=1.3, tiktok_momentum="rising",
         supplier_cost=6, shipping_cost=4, retail_price=32, product_weight_kg=0.5,
         tiktok_hashtag_views=15_000_000, meta_active_advertisers=3, meta_ad_longevity_days=30,
         demo_videos_top10=5, aliexpress_sellers_1k=8, brand_dominance_pct=12, competitor_count=8000,
         diff_unaddressed_themes=2, diff_complement_skus=2, diff_oem_available=1,
         diff_market_fragmented=1, diff_organic_ugc=3, alltime_current_value=42),

    # 17 — heavy -> eliminated by F2
    dict(name="Folding Treadmill", category="fitness", country="US",
         trends_interest=40, amazon_bsr=9000, supplier_cost=120, shipping_cost=60, retail_price=350,
         product_weight_kg=30, longest_dim_cm=140, aliexpress_sellers_1k=5,
         brand_dominance_pct=20, competitor_count=6000, alltime_current_value=45),

    # 18 — mushroom night light
    dict(name="Mushroom Night Light", category="home", country="US",
         trends_interest=25, amazon_bsr=30000, reddit_posts_90d=3, pinterest_saves=900,
         trends_direction_pct=-8, seasonality_ratio=1.6, tiktok_momentum="flat",
         supplier_cost=3, shipping_cost=3, retail_price=16, product_weight_kg=0.2,
         tiktok_hashtag_views=40_000_000, meta_active_advertisers=3, meta_ad_longevity_days=15,
         demo_videos_top10=4, aliexpress_sellers_1k=14, brand_dominance_pct=16, competitor_count=19000,
         diff_unaddressed_themes=0, diff_complement_skus=1, diff_oem_available=1,
         diff_market_fragmented=1, diff_organic_ugc=3, alltime_current_value=35),

    # 19 — partially measured (5 blanks) -> Medium confidence
    dict(name="Ice Roller for Face", category="beauty", country="US",
         trends_interest=32, reddit_posts_90d=5, pinterest_saves=1100,
         trends_direction_pct=14, seasonality_ratio=2.2, tiktok_momentum="rising",
         supplier_cost=2, shipping_cost=2, retail_price=14, product_weight_kg=0.15,
         tiktok_hashtag_views=28_000_000,
         demo_videos_top10=5, aliexpress_sellers_1k=16, brand_dominance_pct=15,
         diff_unaddressed_themes=1, diff_oem_available=1,
         diff_market_fragmented=1, diff_organic_ugc=4, alltime_current_value=40),

    # 20 — premium positioning lifts net + lower competition -> Test (top tier in sample)
    dict(name="Smart Posture Trainer (premium)", category="health", country="US",
         trends_interest=45, amazon_bsr=9000, reddit_posts_90d=8, pinterest_saves=700,
         trends_direction_pct=40, seasonality_ratio=1.3, tiktok_momentum="rising",
         supplier_cost=12, shipping_cost=4, retail_price=59, product_weight_kg=0.1,
         tiktok_hashtag_views=25_000_000, meta_active_advertisers=5, meta_ad_longevity_days=50,
         demo_videos_top10=6, aliexpress_sellers_1k=5, brand_dominance_pct=10, competitor_count=6000,
         diff_unaddressed_themes=2, diff_complement_skus=2, diff_oem_available=1,
         diff_market_fragmented=1, diff_organic_ugc=5, alltime_current_value=55),
]


def seed():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    for p in PRODUCTS:
        insert_product(p)
    logger.info(
        "database_seeded",
        extra={
            "product_count": len(PRODUCTS),
            "database_path": DB_PATH,
        }
    )
    print(f"Seeded {len(PRODUCTS)} products into {DB_PATH}")


if __name__ == "__main__":
    seed()
