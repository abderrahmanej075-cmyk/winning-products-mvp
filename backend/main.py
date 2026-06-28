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
from collections import Counter
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
from sources.ebay import EbayCollector, _stub_response as _ebay_stub
from sources.seeds import SEED_GROUPS, expand_seeds, is_weak_candidate

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


class EbayDiscoverRequest(BaseModel):
    seeds: list
    country: Optional[str] = "US"
    limit_per_seed: Optional[int] = 5


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
        "positive_reasons": res.get("positive_reasons", []),
        "caution_reasons": res.get("caution_reasons", []),
        "filter_reasons": res.get("filter_reasons", []),
        "score_breakdown": res.get("score_breakdown", {}),
    }


_REC_AR = {
    "Strong candidate": "مرشح قوي ⭐",
    "Test with small budget": "اختبر بميزانية صغيرة 🧪",
    "Watchlist": "قيد المراقبة 👁️",
    "Reject": "مرفوض ❌",
}


def _build_arabic_summary(total, counts, eliminated, avg, top_candidates, rejection_summary):
    rejected = counts.get("Reject", 0)
    watchlist = counts.get("Watchlist", 0)
    test = counts.get("Test with small budget", 0)
    strong = counts.get("Strong candidate", 0)

    lines = [
        "تقرير المنتجات اليومي",
        "",
        f"إجمالي المنتجات المحللة: {total}",
        f"مرفوض: {rejected} | قيد المراقبة: {watchlist} | للاختبار: {test} | مرشح قوي: {strong}",
        (f"متوسط النقاط للمنتجات المقبولة: {avg}/60" if avg else "لا توجد بيانات كافية للمتوسط"),
        "",
        "أفضل المنتجات المرشحة:",
    ]

    if top_candidates:
        for i, c in enumerate(top_candidates, 1):
            rec_ar = _REC_AR.get(c["recommendation"], c["recommendation"])
            pos = " | ".join(c.get("positive_reasons", [])) or "لم يُحدَّد"
            caut = " | ".join(c.get("caution_reasons", [])) or "لا تحذيرات"
            net = c.get("net_profit_per_order")
            net_str = f"${net:.2f}" if net is not None else "غير محسوب"
            lines += [
                f"{i}. {c['name']} — {c['score']}/60 — {rec_ar}",
                f"   إيجابيات: {pos}",
                f"   تحذيرات: {caut}",
                f"   صافي الربح المتوقع للطلب: {net_str}",
            ]
    else:
        lines.append("لا توجد منتجات مرشحة حتى الآن.")

    if rejection_summary:
        lines += ["", "أبرز أسباب الرفض:"]
        for item in rejection_summary:
            lines.append(f"  - {item['reason']} (مرات: {item['count']})")

    return "\n".join(lines)


# --------------------------------------------------------------------------- routes
@app.get("/")
def root():
    return {
        "service": "Winning Products MVP",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": ["/products", "/products/{id}", "/products/score",
                      "/discovery/manual", "/discovery/seeds",
                      "/sources/ebay/discover", "/reports/daily", "/health"],
    }


@app.get("/health")
def health_check():
    """Health check endpoint for monitoring and load balancing."""
    return {"status": "ok", "service": "Winning Products MVP"}


@app.get("/health/smoke")
def smoke_test():
    """Lightweight end-to-end check: scoring pipeline returns all expected fields."""
    sample = {
        "name": "Posture Corrector Back Brace",
        "category": "health",
        "country": "US",
        "retail_price": 29.99,
        "supplier_cost": 6.50,
        "shipping_cost": 3.20,
        "product_weight_kg": 0.18,
        "trends_interest": 72,
        "tiktok_momentum": "surging",
    }
    result = scoring.score_product(sample)
    required = {"score", "recommendation", "score_breakdown", "positive_reasons",
                "caution_reasons", "filter_reasons", "eliminated"}
    missing = sorted(required - set(result.keys()))
    return {
        "status": "ok" if not missing else "degraded",
        "missing_keys": missing,
        "sample_score": result.get("score"),
        "sample_recommendation": result.get("recommendation"),
        "positive_reasons": result.get("positive_reasons", []),
        "score_breakdown": result.get("score_breakdown", {}),
    }


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
    country = (prod.country or "US").strip().upper()
    existing = db.fetch_by_name_country(prod.name, country)
    if existing:
        p = dict(existing)
        return {"id": p["id"], "product": p, "scoring": scoring.score_product(p),
                "duplicate": True, "source": "manual", "env": None}
    pid = db.insert_product(prod.model_dump())
    row = db.fetch_by_id(pid)
    p = dict(row)
    return {"id": pid, "product": p, "scoring": scoring.score_product(p),
            "source": "manual", "env": None}


@app.get("/discovery/seeds")
def discovery_seeds():
    """Return all US discovery seed groups and their expanded search queries."""
    total_queries = sum(len(v) for v in SEED_GROUPS.values())
    return {
        "seed_groups": SEED_GROUPS,
        "total_groups": len(SEED_GROUPS),
        "total_queries": total_queries,
        "usage": (
            "Pass any key from seed_groups as a seed to POST /sources/ebay/discover "
            "to auto-expand to specific eBay search queries."
        ),
    }


@app.post("/sources/ebay/discover")
def ebay_discover(req: EbayDiscoverRequest):
    country = req.country or "US"

    # Expand recognized seed group names to specific eBay search queries,
    # then append the original seeds as broad fallback queries so sandbox
    # environments with limited inventory still return results.
    expanded = expand_seeds(req.seeds)
    seen: set = set(expanded)
    combined_queries = list(expanded)
    for s in req.seeds:
        if s not in seen:
            combined_queries.append(s)
            seen.add(s)

    collector = EbayCollector()
    result = collector.discover(
        combined_queries, country=country, limit_per_seed=req.limit_per_seed or 5
    )

    source = result.get("source", "ebay")
    env = result.get("env", "sandbox")
    skipped = list(result.get("skipped", []))

    def _enrich(candidates, src, ev):
        out = []
        for candidate in candidates:
            weak, weak_reason = is_weak_candidate(candidate.get("name", ""))
            if weak:
                skipped.append({"title": candidate.get("name"), "reason": weak_reason})
                continue
            res = scoring.score_product(candidate)
            out.append({
                **candidate,
                "score": res["score"],
                "recommendation": res["recommendation"],
                "score_breakdown": res.get("score_breakdown", {}),
                "positive_reasons": res.get("positive_reasons", []),
                "caution_reasons": res.get("caution_reasons", []),
                "filter_reasons": res.get("filter_reasons", []),
                "source": src,
                "env": ev,
            })
        return out

    enriched = _enrich(result.get("candidates", []), source, env)

    # Zero-result fallback: live eBay returned nothing (no API error, just no
    # inventory match in sandbox). Return stub candidates with a clear note.
    if not enriched and source == "ebay" and settings.ebay_fallback_to_stub:
        stub = _ebay_stub(req.seeds, country)
        enriched = _enrich(stub.get("candidates", []), "ebay_stub_fallback", "stub")
        source = "ebay_stub_fallback"
        env = "stub"
        result["note"] = (
            "Live eBay returned no candidates for expanded queries; "
            "returned stub fallback candidates."
        )

    result["candidates"] = enriched
    result["skipped"] = skipped
    result["source"] = source
    result["env"] = env
    result["expanded_queries"] = combined_queries
    return result


@app.get("/reports/daily")
def daily_report():
    rows = [dict(r) for r in db.fetch_all()]
    scored = [(r, scoring.score_product(r)) for r in rows]

    counts = {"Reject": 0, "Watchlist": 0, "Test with small budget": 0, "Strong candidate": 0}
    eliminated = 0
    totals = []
    rejection_pool: list = []

    for _, res in scored:
        counts[res["recommendation"]] = counts.get(res["recommendation"], 0) + 1
        if res["eliminated"]:
            eliminated += 1
            rejection_pool.extend(res.get("filter_reasons", []))
        elif res["score"] is not None:
            totals.append(res["score"])

    avg = round(sum(totals) / len(totals), 1) if totals else None

    top_pairs = sorted(
        [(r, res) for r, res in scored if not res["eliminated"] and res["score"] is not None],
        key=lambda x: x[1]["score"],
        reverse=True,
    )[:5]

    top_candidates = [
        {
            "name": r["name"],
            "score": res["score"],
            "recommendation": res["recommendation"],
            "positive_reasons": res.get("positive_reasons", []),
            "caution_reasons": res.get("caution_reasons", []),
            "net_profit_per_order": res.get("net_profit_per_order"),
            "score_breakdown": res.get("score_breakdown", {}),
        }
        for r, res in top_pairs
    ]

    reason_counts = Counter(rejection_pool)
    rejection_summary = [
        {"reason": r, "count": c} for r, c in reason_counts.most_common(5)
    ]

    arabic_summary = _build_arabic_summary(
        total=len(rows),
        counts=counts,
        eliminated=eliminated,
        avg=avg,
        top_candidates=top_candidates,
        rejection_summary=rejection_summary,
    )

    return {
        "generated_at_utc": db.now_iso(),
        "total_products": len(rows),
        "eliminated": eliminated,
        "by_recommendation": counts,
        "average_score": avg,
        "top_candidates": top_candidates,
        "rejection_summary": rejection_summary,
        "arabic_summary": arabic_summary,
    }
