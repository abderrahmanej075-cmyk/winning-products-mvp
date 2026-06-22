"""FastAPI backend for the Winning Products MVP.

Endpoints:
  GET  /products            -> list with score + recommendation
  GET  /products/{id}       -> full product + full scoring breakdown
  POST /products/score      -> score an existing product (by id) or an inline product; optional CAC
  POST /discovery/manual    -> manual product input (insert + score)  [the manual input adapter]
  GET  /reports/daily       -> aggregate summary

No external APIs. Scoring is the deterministic V2 engine over stored fields.
"""
import time
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db
import scoring
from config import settings
from logger import logger
from error_handlers import register_error_handlers
from validators import ProductIn as ValidatedProductIn

app = FastAPI(title="Winning Products MVP", version="0.1.0")

# Register error handlers
register_error_handlers(app)

# Configure CORS with settings from .env
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with timing and status."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time

    logger.info(
        "http_request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(process_time * 1000, 2),
        }
    )
    return response


db.init_db()  # ensure the table exists even before seeding


# --------------------------------------------------------------------------- models
class ProductIn(BaseModel):
    name: str
    category: Optional[str] = "other"
    country: Optional[str] = "US"
    trends_interest: Optional[int] = None
    amazon_bsr: Optional[int] = None
    reddit_posts_90d: Optional[int] = None
    pinterest_saves: Optional[int] = None
    trends_direction_pct: Optional[float] = None
    seasonality_ratio: Optional[float] = None
    tiktok_momentum: Optional[str] = None
    supplier_cost: Optional[float] = None
    shipping_cost: Optional[float] = None
    retail_price: Optional[float] = None
    product_weight_kg: Optional[float] = None
    tiktok_hashtag_views: Optional[int] = None
    meta_active_advertisers: Optional[int] = None
    meta_ad_longevity_days: Optional[int] = None
    demo_videos_top10: Optional[int] = None
    aliexpress_sellers_1k: Optional[int] = None
    brand_dominance_pct: Optional[float] = None
    competitor_count: Optional[int] = None
    diff_unaddressed_themes: Optional[int] = None
    diff_complement_skus: Optional[int] = None
    diff_oem_available: Optional[int] = None
    diff_market_fragmented: Optional[int] = None
    diff_organic_ugc: Optional[int] = None
    legal_restricted: Optional[int] = None
    hazmat: Optional[int] = None
    fragile_material: Optional[int] = None
    breakage_mentions: Optional[int] = None
    longest_dim_cm: Optional[float] = None
    seasonality_offpeak: Optional[int] = None
    alltime_current_value: Optional[int] = None


class ScoreRequest(BaseModel):
    product_id: Optional[int] = None
    cac: Optional[float] = None
    product: Optional[ProductIn] = None


# --------------------------------------------------------------------------- helpers
def _summary(row, cac=None):
    p = dict(row)
    res = scoring.score_product(p, cac if cac is not None else scoring.DEFAULT_CAC)
    return {
        "id": p["id"],
        "name": p["name"],
        "category": p.get("category"),
        "country": p.get("country"),
        "score": res["score"],
        "score_max": 60,
        "recommendation": res["recommendation"],
        "confidence": res["confidence"]["level"],
        "net_profit_per_order": res["net_profit_per_order"],
        "eliminated": res["eliminated"],
    }


# --------------------------------------------------------------------------- routes
@app.get("/")
def root():
    return {
        "service": "Winning Products MVP",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": ["/products", "/products/{id}", "/products/score",
                      "/discovery/manual", "/reports/daily", "/health"],
    }


@app.get("/health")
def health_check():
    """Health check endpoint for monitoring and load balancing."""
    return {"status": "ok", "service": "Winning Products MVP"}


@app.get("/products")
def list_products():
    return [_summary(r) for r in db.fetch_all()]


@app.get("/products/{pid}")
def get_product(pid: int):
    row = db.fetch_by_id(pid)
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    p = dict(row)
    return {"product": p, "scoring": scoring.score_product(p)}


@app.post("/products/score")
def score(req: ScoreRequest):
    cac = req.cac if req.cac is not None else scoring.DEFAULT_CAC
    if req.product_id is not None:
        row = db.fetch_by_id(req.product_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Product not found")
        p = dict(row)
    elif req.product is not None:
        p = req.product.model_dump()
    else:
        raise HTTPException(status_code=400, detail="Provide product_id or product")
    return {"input": {"product_id": req.product_id, "cac": cac},
            "scoring": scoring.score_product(p, cac)}


@app.post("/discovery/manual")
def discovery_manual(prod: ProductIn):
    pid = db.insert_product(prod.model_dump())
    row = db.fetch_by_id(pid)
    p = dict(row)
    return {"id": pid, "product": p, "scoring": scoring.score_product(p)}


@app.get("/reports/daily")
def daily_report():
    rows = [dict(r) for r in db.fetch_all()]
    scored = [(r, scoring.score_product(r)) for r in rows]
    counts = {"Reject": 0, "Watchlist": 0, "Test with small budget": 0, "Strong candidate": 0}
    eliminated = 0
    totals = []
    for _, res in scored:
        counts[res["recommendation"]] = counts.get(res["recommendation"], 0) + 1
        if res["eliminated"]:
            eliminated += 1
        elif res["score"] is not None:
            totals.append(res["score"])
    avg = round(sum(totals) / len(totals), 1) if totals else None
    top = sorted(
        [(r["name"], res["score"], res["recommendation"])
         for r, res in scored if not res["eliminated"] and res["score"] is not None],
        key=lambda x: x[1], reverse=True,
    )[:5]
    return {
        "generated_at_utc": db.now_iso(),
        "total_products": len(rows),
        "eliminated": eliminated,
        "by_recommendation": counts,
        "average_score": avg,
        "top_candidates": [{"name": n, "score": s, "recommendation": rec} for n, s, rec in top],
    }
