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
from html import escape as _he
from typing import Any, Optional

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
from sources.registry import REGISTRY, ACTIVE_SOURCES
from sources.normalize import normalize_candidate
from sources.connectors import CONNECTORS, build_readiness_plan

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
    min_acceptable_candidates: Optional[int] = 3   # stop per seed once this many non-Reject found
    max_queries_per_seed: Optional[int] = 5        # max eBay calls per seed
    max_total_candidates: Optional[int] = 20       # global cap across all seeds


class MultisourceDiscoverRequest(BaseModel):
    seeds: list
    country: Optional[str] = "US"
    sources: Optional[list] = ["ebay"]
    limit_per_seed: Optional[int] = 5
    max_queries_per_seed: Optional[int] = 5
    max_total_candidates: Optional[int] = 20
    manual_candidates: Optional[list] = []


class MarketSignalIn(BaseModel):
    product_name: str
    source: str
    country: Optional[str] = "US"
    signal_type: str
    value: Optional[Any] = None
    confidence: Optional[float] = None
    notes: Optional[str] = None
    observed_at_utc: Optional[str] = None


_ALLOWED_EVIDENCE_SOURCES: frozenset = frozenset({
    "google_trends", "amazon", "keepa", "tiktok", "meta",
    "reddit", "youtube", "aliexpress", "cj_dropshipping", "manual",
})

_ALLOWED_SIGNAL_TYPES: frozenset = frozenset({
    "demand", "trend", "competition", "social", "supplier", "pain_point",
})


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


def _build_action_plan(counts: dict, top_candidates: list) -> dict:
    """Derive decision, next actions, and seed suggestions from recommendation counts."""
    strong_or_test = counts.get("Strong candidate", 0) + counts.get("Test with small budget", 0)
    watchlist = counts.get("Watchlist", 0)

    if strong_or_test > 0:
        decision = "test_small_budget"
        decision_reason = (
            "At least one product scored as Test or Strong candidate — "
            "ready for a small-budget ad test."
        )
        next_actions = [
            "Validate supplier cost and lead time for the top candidate.",
            "Confirm shipping weight and dimensions to estimate delivery cost.",
            "Define your ad angle based on the product's positive_reasons.",
            "Start with a $20–$50 test budget on TikTok or Meta ads.",
            "Track add-to-cart rate and cost-per-click for 3–5 days before scaling.",
        ]
        suggested_new_seeds = [
            "posture corrector back support",
            "reusable silicone kitchen set",
            "car organizer seat back",
            "pet hair remover lint roller",
            "under desk cable management",
        ]
    elif watchlist > 0:
        decision = "wait"
        decision_reason = (
            "Candidates reached Watchlist but not Test threshold — "
            "manual review recommended before spending ad budget."
        )
        next_actions = [
            "Review each Watchlist product's caution_reasons carefully.",
            "Check supplier cost and shipping weight for margin viability.",
            "Look for product variants with stronger differentiation.",
            "Run one more discovery pass with more specific seed keywords.",
            "Do not test until at least one product reaches 'Test with small budget' verdict.",
        ]
        suggested_new_seeds = [
            "pet hair remover couch furniture",
            "car seat back organizer kickproof",
            "kitchen cleaning brush scrubber",
            "posture support brace adjustable",
            "travel packing cubes compression",
        ]
    else:
        decision = "change_niche"
        decision_reason = (
            "All discovered products scored as Reject — "
            "seeds are too generic or market data is insufficient."
        )
        next_actions = [
            "Switch to more specific problem-solving seed keywords.",
            "Avoid broad category terms like 'home storage' or 'kitchen organizer'.",
            "Use buyer-pain-point language: 'cat hair remover for couch', 'no-drill shower caddy'.",
            "Increase max_queries_per_seed to 8–10 to explore more eBay results.",
            "Consider adding a known winning product via /discovery/manual for baseline comparison.",
        ]
        suggested_new_seeds = [
            "pet hair remover roller reusable",
            "self cleaning slicker brush dog",
            "car cup holder insert expander",
            "magnetic cabinet lock baby proofing",
            "reusable beeswax food wrap",
        ]

    return {
        "decision": decision,
        "decision_reason": decision_reason,
        "next_actions": next_actions,
        "suggested_new_seeds": suggested_new_seeds,
    }


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
    limit = req.limit_per_seed or 5
    min_ok = req.min_acceptable_candidates or 3
    max_q = req.max_queries_per_seed or 5
    max_total = req.max_total_candidates or 20

    has_live = bool(settings.ebay_client_id and settings.ebay_client_secret)
    collector = EbayCollector()

    all_candidates: list = []
    all_skipped: list = []
    queries_used: list = []
    total_scored = 0
    note = None

    def _score_and_filter(raw_candidates, src, ev):
        nonlocal total_scored
        out = []
        for candidate in raw_candidates:
            weak, reason = is_weak_candidate(candidate.get("name", ""))
            if weak:
                all_skipped.append({"title": candidate.get("name"), "reason": reason})
                continue
            res = scoring.score_product(candidate)
            total_scored += 1
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

    if not has_live:
        # Stub mode — single call, no API loop needed.
        stub = _ebay_stub(req.seeds, country)
        all_skipped.extend(stub.get("skipped", []))
        all_candidates = _score_and_filter(stub.get("candidates", []), "ebay_stub", "stub")
        queries_used = list(req.seeds)
        source, env = "ebay_stub", "stub"

    else:
        # Live mode — quality loop: fire queries one at a time per seed,
        # stop early once enough non-Reject candidates are found.
        source = "ebay"
        env = settings.ebay_env if settings.ebay_env in ("sandbox", "production") else "sandbox"
        seen_names: set = set()

        for seed in req.seeds:
            seed_key = seed.strip().lower()
            # Specific expanded queries first, then the original broad seed as fallback.
            if seed_key in SEED_GROUPS:
                specific = SEED_GROUPS[seed_key][: max_q - 1]
                seed_queries = specific + [seed]
            else:
                seed_queries = [seed]
            seed_queries = seed_queries[:max_q]

            acceptable_from_seed = 0

            for query in seed_queries:
                if len(all_candidates) >= max_total:
                    break
                if acceptable_from_seed >= min_ok:
                    break  # enough quality candidates from this seed

                result = collector.discover([query], country=country, limit_per_seed=limit)
                queries_used.append(query)
                all_skipped.extend(result.get("skipped", []))

                res_src = result.get("source", source)
                res_env = result.get("env", env)

                for c in _score_and_filter(result.get("candidates", []), res_src, res_env):
                    name_key = (c.get("name") or "").strip().lower()
                    if not name_key or name_key in seen_names:
                        continue  # deduplicate across queries
                    seen_names.add(name_key)
                    all_candidates.append(c)
                    if c.get("recommendation") not in ("Reject", None):
                        acceptable_from_seed += 1
                    if len(all_candidates) >= max_total:
                        break

        # Zero-result fallback when sandbox yields nothing at all.
        if not all_candidates and settings.ebay_fallback_to_stub:
            stub = _ebay_stub(req.seeds, country)
            all_candidates = _score_and_filter(
                stub.get("candidates", []), "ebay_stub_fallback", "stub"
            )
            source, env = "ebay_stub_fallback", "stub"
            note = (
                "Live eBay returned no candidates for expanded queries; "
                "returned stub fallback candidates."
            )

    # Sort by score descending; None (eliminated) sorts last.
    all_candidates.sort(
        key=lambda c: (c.get("score") is not None, c.get("score") or 0),
        reverse=True,
    )

    # Quality metadata
    _REC_RANK = {"Strong candidate": 0, "Test with small budget": 1, "Watchlist": 2, "Reject": 3}
    best_rec = None
    if all_candidates:
        best_rec = min(
            (c.get("recommendation") or "Reject" for c in all_candidates),
            key=lambda r: _REC_RANK.get(r, 99),
        )

    non_reject = [
        c for c in all_candidates if c.get("recommendation") not in ("Reject", None)
    ]
    if not all_candidates:
        quality_status = "empty"
    elif non_reject:
        if any(
            c.get("recommendation") in ("Strong candidate", "Test with small budget")
            for c in non_reject
        ):
            quality_status = "good"
        else:
            quality_status = "watchlist_only"
    else:
        quality_status = "weak"
        if not note:
            note = (
                "Only reject-level candidates found; "
                "broaden seeds or increase query count."
            )

    if quality_status == "weak" or quality_status == "empty":
        discovery_suggestions = [
            "Use more specific problem-solving seed keywords.",
            "Avoid broad generic storage terms.",
            "Try niche categories with clear buyer pain points.",
            "Increase max_queries_per_seed to explore more eBay results.",
            "Try seeds like: pet hair remover, car organizer, kitchen cleaning tool, or posture support.",
        ]
    elif quality_status == "watchlist_only":
        discovery_suggestions = [
            "Review Watchlist products manually before testing.",
            "Look for products with stronger differentiation.",
            "Check shipping size, fragility, and supplier margin before testing.",
        ]
    else:  # "good"
        discovery_suggestions = [
            "Review top candidates and test the highest scoring product first.",
        ]

    resp = {
        "candidates": all_candidates,
        "skipped": all_skipped,
        "source": source,
        "env": env,
        "expanded_queries": queries_used,
        "total_queries_used": len(queries_used),
        "total_candidates_scored": total_scored,
        "best_recommendation": best_rec,
        "quality_status": quality_status,
        "discovery_suggestions": discovery_suggestions,
    }
    if note:
        resp["note"] = note
    return resp


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

    # Normalize top candidates into the shared multi-source signal shape.
    # net_profit_per_order and score_breakdown are appended for backward compat.
    top_candidates = []
    for r, res in top_pairs:
        norm = normalize_candidate(
            r,
            source=r.get("source", "manual"),
            score_result=res,
        )
        top_candidates.append({
            **norm,
            "net_profit_per_order": res.get("net_profit_per_order"),
            "score_breakdown": res.get("score_breakdown", {}),
        })

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

    action_plan = _build_action_plan(counts, top_candidates)

    # Multi-source metadata
    # eBay is the default discovery source; "manual" is only added when the DB contains
    # products that explicitly carry source="manual" (e.g. direct /discovery/manual entries
    # that have not been enriched from eBay).
    db_sources = list({r.get("source", "ebay") for r in rows}) if rows else ["ebay"]
    sources_used = sorted(set(db_sources)) or ["ebay"]
    source_breakdown = {}
    for r in rows:
        src = r.get("source", "ebay")
        source_breakdown[src] = source_breakdown.get(src, 0) + 1
    missing_sources = [
        {
            "source": k,
            "status": v["status"],
            "signal": v["signal"],
            "note": v["notes"],
        }
        for k, v in REGISTRY.items()
        if v["status"] == "placeholder"
    ]

    # Quality status from recommendation distribution
    strong_or_test = counts.get("Strong candidate", 0) + counts.get("Test with small budget", 0)
    watchlist = counts.get("Watchlist", 0)
    if not rows:
        quality_status = "empty"
    elif strong_or_test > 0:
        quality_status = "good"
    elif watchlist > 0:
        quality_status = "watchlist_only"
    else:
        quality_status = "weak"

    # Best recommendation across all non-eliminated products
    _REC_RANK = {"Strong candidate": 0, "Test with small budget": 1, "Watchlist": 2, "Reject": 3}
    non_eliminated = [res for _, res in scored if not res["eliminated"]]
    best_rec = (
        min(
            (res.get("recommendation") or "Reject" for res in non_eliminated),
            key=lambda r: _REC_RANK.get(r, 99),
        )
        if non_eliminated
        else None
    )

    # Data completeness based on key signal fields
    _SIGNAL_CHECK = (
        "trends_interest", "amazon_bsr", "tiktok_hashtag_views",
        "supplier_cost", "tiktok_momentum",
    )
    fields_present = sum(1 for r in rows for f in _SIGNAL_CHECK if r.get(f) is not None)
    total_possible = len(rows) * len(_SIGNAL_CHECK)
    if not rows:
        data_completeness_note = (
            "No products in database. Add products via /discovery/manual "
            "or run /discovery/multisource."
        )
    elif fields_present == 0:
        data_completeness_note = (
            "No demand, trend, or supplier signal data found. "
            "Scores rely on Low confidence capping. "
            "Enrich products via /discovery/manual or run /discovery/multisource."
        )
    elif fields_present < total_possible // 2:
        pct = round(fields_present / total_possible * 100)
        data_completeness_note = (
            f"Partial signal data ({pct}% of key fields present). "
            "Products with missing signals are scored at Low or Medium confidence."
        )
    else:
        data_completeness_note = (
            "Good signal coverage. Scores reflect available demand, trend, and supplier data."
        )

    # Enrich top candidates with evidence — load all records once, then match per candidate
    all_evidence = db.fetch_evidence()
    matched_ev_ids: set = set()
    for candidate in top_candidates:
        matched = _match_evidence_to_candidate(all_evidence, candidate.get("name", ""))
        ev_summary = _build_candidate_evidence_summary(matched)
        candidate["market_evidence"] = matched
        candidate["evidence_count"] = ev_summary["evidence_count"]
        candidate["evidence_sources"] = ev_summary["evidence_sources"]
        candidate["evidence_signals"] = ev_summary["evidence_signals"]
        candidate["evidence_confidence_avg"] = ev_summary["evidence_confidence_avg"]
        candidate["evidence_notes"] = ev_summary["evidence_notes"]
        candidate["evidence_boost_note"] = ev_summary["evidence_boost_note"]
        # Append high-confidence evidence reasons to positive_reasons (no score change)
        for reason in ev_summary["evidence_positive_reasons"]:
            if reason not in candidate.get("positive_reasons", []):
                candidate.setdefault("positive_reasons", []).append(reason)
        for ev in matched:
            if ev.get("id") is not None:
                matched_ev_ids.add(ev["id"])

    # Evidence summary for the report
    ev_stats = db.fetch_evidence_stats()
    matched_ev_count = len(matched_ev_ids)
    evidence_summary = {
        "total_evidence_count": ev_stats["total"],
        "active_evidence_count": ev_stats["active"],
        "accepted_evidence_count": ev_stats["accepted"],
        "weak_evidence_count": ev_stats["weak"],
        "rejected_evidence_count": ev_stats["rejected"],
        "duplicate_evidence_count": ev_stats["duplicate"],
        "matched_evidence_count": matched_ev_count,
        "unmatched_evidence_count": max(0, ev_stats["total"] - matched_ev_count),
        "sources_present": db.fetch_evidence_sources(),
        "latest_observed_at_utc": db.latest_evidence_observed_at(),
        "note": (
            "Active evidence matched to top candidates. External API connections not yet active."
            if matched_ev_count > 0
            else (
                "Evidence stored but no active match found for top candidates."
                if ev_stats["active"] > 0
                else "No evidence stored yet. Use POST /evidence/market-signal to add signals."
            )
        ),
    }

    return {
        "generated_at_utc": db.now_iso(),
        "total_products": len(rows),
        "eliminated": eliminated,
        "by_recommendation": counts,
        "average_score": avg,
        "top_candidates": top_candidates,
        "rejection_summary": rejection_summary,
        "arabic_summary": arabic_summary,
        "summary_ar": arabic_summary,
        "decision": action_plan["decision"],
        "decision_reason": action_plan["decision_reason"],
        "next_actions": action_plan["next_actions"],
        "suggested_new_seeds": action_plan["suggested_new_seeds"],
        "sources_used": sources_used,
        "source_breakdown": source_breakdown,
        "missing_sources": missing_sources,
        "quality_status": quality_status,
        "best_recommendation": best_rec,
        "data_completeness_note": data_completeness_note,
        "evidence_summary": evidence_summary,
        "source_readiness_plan": build_readiness_plan(),
    }


# --------------------------------------------------------------------------- evidence helpers
import re as _re


def _norm_name(s: str) -> str:
    """Lowercase, trim, and collapse internal whitespace for name comparison."""
    return _re.sub(r'\s+', ' ', (s or '').lower().strip())


def _match_evidence_to_candidate(all_evidence: list, candidate_name: str) -> list:
    """Return evidence records whose product_name meaningfully matches the candidate name.

    Matching rules (all after normalization):
      1. Exact match
      2. Evidence product_name is fully contained in the candidate name (len >= 8)
      3. Candidate name is fully contained in the evidence product_name (len >= 8)

    The minimum-length guard on partial matches prevents over-matching on
    short generic words like "bag" or "set".
    """
    cname = _norm_name(candidate_name)
    if not cname:
        return []
    matched = []
    for ev in all_evidence:
        ev_name = _norm_name(ev.get("product_name", ""))
        if not ev_name:
            continue
        if ev_name == cname:
            matched.append(ev)
        elif len(ev_name) >= 8 and ev_name in cname:
            matched.append(ev)
        elif len(cname) >= 8 and cname in ev_name:
            matched.append(ev)
    return matched


_BOOST_SIGNAL_TYPES: frozenset = frozenset({
    "demand", "trend", "social", "pain_point", "supplier", "competition"
})


def _build_candidate_evidence_summary(matched: list) -> dict:
    """Summarize matched evidence records for one candidate.

    Only is_active=True evidence affects scoring. Accepted evidence (confidence >= 0.7,
    approved signal_type) adds to positive_reasons. Weak evidence appears in evidence_notes
    only. Rejected and duplicate evidence are excluded entirely. Numeric score is never
    modified by evidence.
    """
    # Split by quality gate — rejected/duplicate are excluded (is_active=False)
    active = [e for e in matched if e.get("is_active", True)]
    if not active:
        return {
            "evidence_count": 0,
            "evidence_sources": [],
            "evidence_signals": [],
            "evidence_confidence_avg": None,
            "evidence_notes": [],
            "evidence_boost_note": "",
            "evidence_positive_reasons": [],
        }

    accepted = [e for e in active if (e.get("quality_status") or "accepted") in ("accepted",)]
    weak = [e for e in active if e.get("quality_status") == "weak"]

    # Positive reasons from high-confidence accepted evidence only
    high_conf = [
        e for e in accepted
        if (e.get("confidence") or 0.0) >= 0.7
        and e.get("signal_type") in _BOOST_SIGNAL_TYPES
    ]
    ev_reasons = [
        f"Manual evidence ({ev['source']}): {ev['signal_type']} = {ev['value']} "
        f"(confidence {ev['confidence']})"
        for ev in high_conf
    ]

    # Evidence notes from weak evidence + stored notes from all active records
    ev_notes: list = []
    for ev in weak:
        reason_text = ", ".join(ev.get("quality_reasons") or []) or "low confidence"
        ev_notes.append(
            f"Weak signal ({ev['source']}): {ev['signal_type']} = {ev['value']} — {reason_text}"
        )
    for ev in active:
        if ev.get("notes"):
            ev_notes.append(ev["notes"])

    if high_conf:
        boost_note = (
            f"High-confidence evidence from "
            f"{', '.join(sorted({e['source'] for e in high_conf}))} "
            f"supports {', '.join(sorted({e['signal_type'] for e in high_conf}))} signal(s). "
            "Added to positive reasons; numeric score unchanged."
        )
    elif weak:
        boost_note = (
            "Only weak evidence available — no scoring boost applied. "
            "See evidence_notes for details."
        )
    else:
        boost_note = (
            "Evidence stored but confidence or signal type below threshold — "
            "no score influence applied."
        )

    sources = sorted({e["source"] for e in active})
    signals = sorted({e["signal_type"] for e in active})
    confidences = [e["confidence"] for e in active if e.get("confidence") is not None]
    conf_avg = round(sum(confidences) / len(confidences), 2) if confidences else None

    return {
        "evidence_count": len(active),
        "evidence_sources": sources,
        "evidence_signals": signals,
        "evidence_confidence_avg": conf_avg,
        "evidence_notes": ev_notes,
        "evidence_boost_note": boost_note,
        "evidence_positive_reasons": ev_reasons,
    }


# --------------------------------------------------------------------------- delivery payload helper
_FUTURE_INTEGRATIONS = {
    "google_trends": {
        "status": "planned",
        "purpose": "Add search trend interest, 12-month direction, and seasonality ratio signals",
        "requires_credentials": False,
        "current_behavior": "not connected yet",
    },
    "amazon_or_keepa": {
        "status": "planned",
        "purpose": "Add Best Seller Rank (BSR), competitor count, and review volume signals",
        "requires_credentials": True,
        "current_behavior": "not connected yet",
    },
    "social_tiktok_meta": {
        "status": "planned",
        "purpose": "Add TikTok hashtag views, TikTok momentum, and Meta active advertiser signals",
        "requires_credentials": True,
        "current_behavior": "not connected yet",
    },
    "reddit_youtube": {
        "status": "planned",
        "purpose": "Add buyer pain point signals from Reddit posts and YouTube review volume",
        "requires_credentials": True,
        "current_behavior": "not connected yet",
    },
    "supplier_sources": {
        "status": "planned",
        "purpose": "Add supplier cost, AliExpress seller count, and lead time from CJ or AliExpress",
        "requires_credentials": False,
        "current_behavior": "not connected yet",
    },
    "google_sheets": {
        "status": "planned",
        "purpose": "Deliver sheet_rows directly to a Google Sheet via n8n or Sheets API",
        "requires_credentials": True,
        "current_behavior": "not connected yet",
    },
    "email": {
        "status": "planned",
        "purpose": "Send email_body_html and email_body_text to a recipient via n8n or SMTP",
        "requires_credentials": True,
        "current_behavior": "not connected yet",
    },
    "notion": {
        "status": "planned",
        "purpose": "Create or update a Notion database with top candidates and daily report data",
        "requires_credentials": True,
        "current_behavior": "not connected yet",
    },
}


def _build_delivery_payload(report: dict) -> dict:
    """Convert the daily report dict into a delivery-ready payload for n8n and future integrations."""
    top = report.get("top_candidates", [])
    sources_used = report.get("sources_used", [])
    missing_sources = report.get("missing_sources", [])
    next_actions = report.get("next_actions", [])
    seeds = report.get("suggested_new_seeds", [])
    decision = report.get("decision", "")
    decision_reason = report.get("decision_reason", "")
    quality_status = report.get("quality_status", "")
    summary_ar = report.get("summary_ar", "")
    data_note = report.get("data_completeness_note", "")
    generated_at = report.get("generated_at_utc", "")
    evidence_summary = report.get("evidence_summary", {})

    missing_names = [m.get("source", "") for m in missing_sources]

    # ---- plain text body ----
    text_lines = [
        "Winning Products Daily Report",
        "=" * 40,
        f"Generated: {generated_at}",
        "",
        f"Decision: {decision.upper()}",
        decision_reason,
        "",
        f"Data Completeness: {data_note}",
        f"Sources Used: {', '.join(sources_used)}",
        f"Signals Not Yet Connected: {', '.join(missing_names) or 'none'}",
        "",
        "--- Arabic Summary ---",
        summary_ar,
        "",
        "--- Next Actions ---",
    ]
    for i, action in enumerate(next_actions, 1):
        text_lines.append(f"{i}. {action}")
    text_lines += ["", "--- Suggested Seeds ---"]
    for seed in seeds:
        text_lines.append(f"- {seed}")
    text_lines += ["", "--- Top Candidates ---"]
    for c in top:
        pos = " | ".join(c.get("positive_reasons", [])) or "none"
        cau = " | ".join(c.get("caution_reasons", []) + c.get("filter_reasons", [])) or "none"
        text_lines += [
            f"{c.get('name')} | Score: {c.get('score')}/60 | {c.get('recommendation')} | Source: {c.get('source')}",
            f"  Positive: {pos}",
            f"  Caution : {cau}",
            f"  Margin signal: {c.get('margin_signal')} | Demand: {c.get('demand_signal')} | Trend: {c.get('trend_signal')}",
            "",
        ]
    email_body_text = "\n".join(text_lines)

    # ---- HTML body ----
    def _li_items(items: list) -> str:
        return "".join(f"<li>{_he(str(item))}</li>" for item in items)

    candidates_html = ""
    for c in top:
        pos_html = _li_items(c.get("positive_reasons", []) or ["none"])
        cau_items = c.get("caution_reasons", []) + c.get("filter_reasons", [])
        cau_html = _li_items(cau_items or ["none"])
        candidates_html += (
            f'<div style="border:1px solid #ddd;border-radius:4px;padding:12px;margin-bottom:12px;">'
            f'<strong>{_he(str(c.get("name", "")))} </strong>'
            f'<span style="color:#555;">{_he(str(c.get("score", "??")))}/60 &mdash; {_he(str(c.get("recommendation", "")))}</span>'
            f'<br><small style="color:#888;">Source: {_he(str(c.get("source", "")))} | '
            f'Demand: {_he(str(c.get("demand_signal", "")))} | '
            f'Trend: {_he(str(c.get("trend_signal", "")))} | '
            f'Margin: {_he(str(c.get("margin_signal", "")))}</small>'
            f'<ul style="margin:6px 0 2px;">{pos_html}</ul>'
            f'<ul style="margin:2px 0;color:#b00;">{cau_html}</ul>'
            f'</div>'
        )

    email_body_html = (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
        '<title>Winning Products Daily Report</title>'
        '</head>'
        '<body style="font-family:Arial,Helvetica,sans-serif;max-width:700px;margin:0 auto;padding:16px;color:#222;">'
        '<h1 style="border-bottom:2px solid #222;padding-bottom:8px;">Winning Products Daily Report</h1>'
        f'<h2 style="color:#333;">Decision: {_he(decision.upper())}</h2>'
        f'<p style="background:#f5f5f5;padding:12px;border-left:4px solid #555;">{_he(decision_reason)}</p>'
        '<h2 style="color:#333;">Arabic Summary</h2>'
        f'<pre style="background:#f5f5f5;padding:12px;white-space:pre-wrap;direction:rtl;text-align:right;">{_he(summary_ar)}</pre>'
        '<h2 style="color:#333;">Data &amp; Sources</h2>'
        f'<p>{_he(data_note)}</p>'
        f'<p><strong>Sources Used:</strong> {_he(", ".join(sources_used))}</p>'
        f'<p><strong>Signals Not Yet Connected:</strong> {_he(", ".join(missing_names) or "none")}</p>'
        '<h2 style="color:#333;">Next Actions</h2>'
        f'<ol>{"".join(f"<li>{_he(a)}</li>" for a in next_actions)}</ol>'
        '<h2 style="color:#333;">Suggested Seeds to Try Next</h2>'
        f'<ul>{"".join(f"<li>{_he(s)}</li>" for s in seeds)}</ul>'
        '<h2 style="color:#333;">Top Candidates</h2>'
        f'{candidates_html}'
        f'<hr><p style="color:#888;font-size:0.85em;">Generated: {_he(generated_at)}</p>'
        '</body></html>'
    )

    # ---- sheet rows ----
    sheet_rows = [
        {
            "generated_at_utc": generated_at,
            "source": c.get("source", ""),
            "product_name": c.get("name", ""),
            "score": c.get("score"),
            "recommendation": c.get("recommendation", ""),
            "decision": decision,
            "decision_reason": decision_reason,
            "quality_status": quality_status,
            "retail_price": c.get("retail_price"),
            "shipping_cost": c.get("shipping_cost"),
            "estimated_margin": c.get("estimated_margin"),
            "demand_signal": c.get("demand_signal", ""),
            "trend_signal": c.get("trend_signal", ""),
            "competition_signal": c.get("competition_signal", ""),
            "supplier_signal": c.get("supplier_signal", ""),
            "margin_signal": c.get("margin_signal", ""),
            "positive_reasons": " | ".join(c.get("positive_reasons", [])),
            "caution_reasons": " | ".join(c.get("caution_reasons", [])),
            "filter_reasons": " | ".join(c.get("filter_reasons", [])),
            "missing_data": ", ".join(c.get("missing_data", [])),
        }
        for c in top
    ]

    email_subject = "Winning Products Daily Report - Action Plan"

    n8n_payload = {
        "subject": email_subject,
        "text": email_body_text,
        "html": email_body_html,
        "rows": sheet_rows,
        "decision": decision,
        "quality_status": quality_status,
        "sources_used": sources_used,
        "top_candidates_count": len(top),
        "suggested_new_seeds": seeds,
    }

    top_candidates_count = len(top)
    sheet_rows_count = len(sheet_rows)

    warnings: list = []
    errors: list = []

    if top_candidates_count == 0:
        delivery_status = "needs_review"
        warnings.append(
            "No top candidates found — run /discovery/multisource or add products via "
            "/discovery/manual before delivering."
        )
    else:
        delivery_status = "ready"

    # Warn when key signals are missing across most top candidates
    missing_signal_count = sum(
        1 for c in top
        for sig in ("demand_signal", "trend_signal", "supplier_signal")
        if c.get(sig) == "missing"
    )
    if missing_signal_count > 0:
        warnings.append(
            f"{missing_signal_count} signal value(s) missing across top candidates — "
            "scores rely on Low confidence capping. "
            "Enrich products via /discovery/manual or add external data sources."
        )

    delivery_channels = ["email", "google_sheets", "notion", "n8n"]

    return {
        "payload_version": "2F-D",
        "generated_at_utc": generated_at,
        "delivery_status": delivery_status,
        "delivery_channels": delivery_channels,
        "top_candidates_count": top_candidates_count,
        "sheet_rows_count": sheet_rows_count,
        "warnings": warnings,
        "errors": errors,
        "email_subject": email_subject,
        "email_body_text": email_body_text,
        "email_body_html": email_body_html,
        "sheet_rows": sheet_rows,
        "n8n_payload": n8n_payload,
        "future_integrations": _FUTURE_INTEGRATIONS,
        "evidence_summary": evidence_summary,
    }


@app.get("/sources")
def list_sources():
    """Return all registered discovery sources with status and signal description."""
    return {"sources": list(REGISTRY.values())}


@app.get("/sources/connectors/health")
def connectors_health():
    """Return health, status, and credential readiness for every registered source connector.

    Covers all 11 potential data sources: ebay, manual, google_trends, reddit, youtube,
    amazon, keepa, aliexpress, cj_dropshipping, tiktok, and meta.
    No external API calls are made. All checks are local (env var presence only).
    """
    return {
        "generated_at_utc": db.now_iso(),
        "connectors": {name: c.check() for name, c in CONNECTORS.items()},
        "source_readiness_plan": build_readiness_plan(),
    }


@app.post("/discovery/multisource")
def multisource_discover(req: MultisourceDiscoverRequest):
    """Collect, normalize, and score candidates from one or more active sources.

    Placeholder sources are listed in missing_sources rather than causing errors.
    All candidates are normalized into the shared multi-source signal shape.
    """
    country = req.country or "US"
    requested_sources = list(req.sources) if req.sources else ["ebay"]
    limit = req.limit_per_seed or 5
    max_q = req.max_queries_per_seed or 5
    max_total = req.max_total_candidates or 20

    # Classify each requested source as active, placeholder/planned, or unknown.
    # ACTIVE_SOURCES comes from the legacy REGISTRY; CONNECTORS covers the full set
    # of planned future sources (google_trends, reddit, amazon, etc.).
    sources_used: list = []
    missing_sources: list = []
    for src in requested_sources:
        if src in ACTIVE_SOURCES:
            sources_used.append(src)
        elif src in REGISTRY:
            missing_sources.append({
                "source": src,
                "note": "Source is configured as placeholder and not yet active.",
            })
        elif src in CONNECTORS:
            connector = CONNECTORS[src]
            missing_env = connector._missing_env_vars()
            missing_sources.append({
                "source": src,
                "note": (
                    f"Planned connector — not yet implemented. "
                    f"Required env vars: {connector.required_env_vars or 'none'}. "
                    f"Missing: {missing_env or 'n/a'}."
                ),
            })
        else:
            missing_sources.append({
                "source": src,
                "note": (
                    f"Unknown source '{src}' — not in connector registry. "
                    "See GET /sources/connectors/health for supported sources."
                ),
            })

    all_candidates: list = []
    source_breakdown: dict = {}
    seen_names: set = set()

    # eBay collection — mirrors the stub/fallback logic in /sources/ebay/discover
    if "ebay" in sources_used:
        has_live_ebay = bool(settings.ebay_client_id and settings.ebay_client_secret)
        ebay_env = (
            settings.ebay_env if settings.ebay_env in ("sandbox", "production") else "sandbox"
        )

        def _add_ebay_candidates(raw_list: list, src: str, qry: str = "") -> None:
            """Filter, score, normalize, and deduplicate raw eBay candidates in-place."""
            for raw in raw_list:
                if len(all_candidates) >= max_total:
                    break
                weak, _ = is_weak_candidate(raw.get("name", ""))
                if weak:
                    continue
                name_key = (raw.get("name") or "").strip().lower()
                if not name_key or name_key in seen_names:
                    continue
                seen_names.add(name_key)
                sr = scoring.score_product(raw)
                all_candidates.append(
                    normalize_candidate(raw, source=src, query=qry, score_result=sr)
                )
                source_breakdown[src] = source_breakdown.get(src, 0) + 1

        if not has_live_ebay:
            # No credentials — use stub immediately (same as /sources/ebay/discover stub mode)
            stub = _ebay_stub(req.seeds, country)
            _add_ebay_candidates(
                stub.get("candidates", []),
                "ebay_stub",
                req.seeds[0] if req.seeds else "",
            )
        else:
            collector = EbayCollector()
            for seed in req.seeds:
                seed_key = seed.strip().lower()
                seed_queries = (SEED_GROUPS.get(seed_key, []) + [seed])[:max_q]
                for query in seed_queries:
                    if len(all_candidates) >= max_total:
                        break
                    result = collector.discover([query], country=country, limit_per_seed=limit)
                    _add_ebay_candidates(
                        result.get("candidates", []),
                        result.get("source", "ebay"),
                        query,
                    )

            # Stub fallback when live eBay sandbox returns no usable candidates
            if not all_candidates and settings.ebay_fallback_to_stub:
                stub = _ebay_stub(req.seeds, country)
                _add_ebay_candidates(
                    stub.get("candidates", []),
                    "ebay_stub_fallback",
                    req.seeds[0] if req.seeds else "",
                )

    # Manual candidates (from request body)
    if "manual" in sources_used and req.manual_candidates:
        for mc in req.manual_candidates:
            if len(all_candidates) >= max_total:
                break
            name_key = (mc.get("name") or "").strip().lower()
            if not name_key or name_key in seen_names:
                continue
            seen_names.add(name_key)
            sr = scoring.score_product(mc)
            all_candidates.append(
                normalize_candidate(
                    mc, source="manual", query=mc.get("query", ""), score_result=sr
                )
            )
            source_breakdown["manual"] = source_breakdown.get("manual", 0) + 1

    # Sort by score descending (scored candidates first)
    all_candidates.sort(
        key=lambda c: (c.get("score") is not None, c.get("score") or 0),
        reverse=True,
    )

    # Quality status
    _REC_RANK = {"Strong candidate": 0, "Test with small budget": 1, "Watchlist": 2, "Reject": 3}
    best_rec = None
    if all_candidates:
        best_rec = min(
            (c.get("recommendation") or "Reject" for c in all_candidates),
            key=lambda r: _REC_RANK.get(r, 99),
        )

    non_reject = [
        c for c in all_candidates if c.get("recommendation") not in ("Reject", None)
    ]
    if not all_candidates:
        quality_status = "empty"
    elif non_reject:
        quality_status = (
            "good"
            if any(
                c.get("recommendation") in ("Strong candidate", "Test with small budget")
                for c in non_reject
            )
            else "watchlist_only"
        )
    else:
        quality_status = "weak"

    if quality_status in ("weak", "empty"):
        discovery_suggestions = [
            "Use more specific problem-solving seed keywords.",
            "Avoid broad generic storage terms.",
            "Try niche categories with clear buyer pain points.",
            "Increase max_queries_per_seed to explore more eBay results.",
            "Try seeds like: pet hair remover, car organizer, kitchen cleaning tool, or posture support.",
        ]
    elif quality_status == "watchlist_only":
        discovery_suggestions = [
            "Review Watchlist products manually before testing.",
            "Look for products with stronger differentiation.",
            "Check shipping size, fragility, and supplier margin before testing.",
        ]
    else:
        discovery_suggestions = [
            "Review top candidates and test the highest scoring product first.",
        ]

    return {
        "generated_at_utc": db.now_iso(),
        "country": country,
        "sources_requested": requested_sources,
        "sources_used": sources_used,
        "missing_sources": missing_sources,
        "source_breakdown": source_breakdown,
        "candidates": all_candidates,
        "top_candidates": all_candidates[:5],
        "quality_status": quality_status,
        "best_recommendation": best_rec,
        "discovery_suggestions": discovery_suggestions,
        "source_readiness_plan": build_readiness_plan(),
    }


@app.get("/reports/daily/delivery/health")
def daily_report_delivery_health():
    """Preflight health check for the n8n delivery workflow.

    Calls the delivery endpoint and returns a compact summary so n8n can verify
    readiness before attempting email, sheet, or Notion delivery.
    No external API calls are made.
    """
    delivery = daily_report_delivery()
    return {
        "ok": delivery.get("delivery_status") == "ready",
        "payload_version": delivery.get("payload_version"),
        "delivery_endpoint": "/reports/daily/delivery",
        "daily_report_endpoint": "/reports/daily",
        "generated_at_utc": delivery.get("generated_at_utc"),
        "delivery_status": delivery.get("delivery_status"),
        "top_candidates_count": delivery.get("top_candidates_count"),
        "sheet_rows_count": delivery.get("sheet_rows_count"),
        "channels_ready": delivery.get("delivery_channels"),
        "warnings": delivery.get("warnings"),
        "errors": delivery.get("errors"),
    }


@app.get("/reports/daily/delivery")
def daily_report_delivery():
    """Return a delivery-ready payload built from the daily report.

    Includes email text, HTML, sheet rows for Google Sheets/CSV, and an n8n_payload.
    All content is generated from the current database state — no external API calls.
    """
    report = daily_report()
    return _build_delivery_payload(report)


# --------------------------------------------------------------------------- evidence quality helper

def _compute_evidence_quality(data: dict) -> dict:
    """Return quality_status, quality_score, quality_reasons, and is_active for a new evidence record."""
    product_name = (data.get("product_name") or "").strip()
    source = (data.get("source") or "").strip()
    signal_type = (data.get("signal_type") or "").strip()
    confidence = data.get("confidence")
    notes = (data.get("notes") or "").strip()

    hard_reasons: list = []
    if not product_name:
        hard_reasons.append("Empty product_name — cannot match to candidate.")
    if not source:
        hard_reasons.append("Empty source field.")
    elif source not in _ALLOWED_EVIDENCE_SOURCES:
        hard_reasons.append(f"Unknown source '{source}' — not in allowed list.")
    if not signal_type:
        hard_reasons.append("Empty signal_type field.")
    elif signal_type not in _ALLOWED_SIGNAL_TYPES:
        hard_reasons.append(f"Unknown signal_type '{signal_type}' — not in allowed list.")

    if hard_reasons:
        return {
            "quality_status": "rejected",
            "quality_score": max(0, 20 - len(hard_reasons) * 8),
            "quality_reasons": hard_reasons,
            "is_active": False,
        }

    reasons: list = []

    if confidence is None:
        reasons.append("No confidence value provided — treating as weak signal.")
        return {"quality_status": "weak", "quality_score": 50, "quality_reasons": reasons, "is_active": True}

    if confidence >= 0.7:
        return {
            "quality_status": "accepted",
            "quality_score": min(100, round(70 + confidence * 30)),
            "quality_reasons": reasons,
            "is_active": True,
        }

    if confidence >= 0.4:
        reasons.append(
            f"Moderate confidence ({confidence}) — between 0.4 and 0.69. "
            "Signal will appear in evidence_notes only, not as a scoring boost."
        )
        return {
            "quality_status": "weak",
            "quality_score": round(confidence * 80),
            "quality_reasons": reasons,
            "is_active": True,
        }

    # confidence < 0.4
    reasons.append(f"Low confidence ({confidence}) — below 0.4 threshold.")
    if source == "manual" and notes:
        reasons.append("Manual source with non-empty notes: stored as weak rather than rejected.")
        return {"quality_status": "weak", "quality_score": 25, "quality_reasons": reasons, "is_active": True}

    return {
        "quality_status": "rejected",
        "quality_score": round(confidence * 40),
        "quality_reasons": reasons,
        "is_active": False,
    }


# --------------------------------------------------------------------------- evidence routes

@app.post("/evidence/market-signal")
def add_market_signal(data: MarketSignalIn):
    """Store one market evidence signal for a named product with quality assessment.

    Computes quality_status (accepted/weak/rejected/duplicate) and stores it alongside
    the evidence. No external API calls are made.
    """
    if data.confidence is not None and not (0.0 <= data.confidence <= 1.0):
        raise HTTPException(
            status_code=422,
            detail=f"confidence must be between 0.0 and 1.0, got {data.confidence}",
        )

    quality = _compute_evidence_quality(data.model_dump())

    # Check for duplicates only when the evidence is structurally valid
    duplicate_of = None
    if quality["quality_status"] != "rejected" and (data.product_name or "").strip():
        duplicate_of = db.find_duplicate_evidence(
            product_name=data.product_name,
            source=data.source,
            country=data.country or "US",
            signal_type=data.signal_type,
            value=str(data.value) if data.value is not None else None,
        )
        if duplicate_of is not None:
            quality = {
                "quality_status": "duplicate",
                "quality_score": quality["quality_score"],
                "quality_reasons": [
                    f"Duplicate of evidence id={duplicate_of} — same product_name, source, "
                    "country, signal_type, and value already stored as active evidence."
                ],
                "is_active": False,
            }

    return db.insert_evidence(data.model_dump(), quality=quality, duplicate_of=duplicate_of)


@app.get("/evidence/market-signal")
def get_market_signals(
    product_name: Optional[str] = None,
    source: Optional[str] = None,
    signal_type: Optional[str] = None,
    country: Optional[str] = None,
):
    """Return stored market evidence, optionally filtered by product_name, source, signal_type, country."""
    return db.fetch_evidence(
        product_name=product_name,
        source=source,
        signal_type=signal_type,
        country=country,
    )


@app.get("/evidence/market-signal/health")
def market_signal_health():
    """Health check for the market evidence intake layer with quality breakdown."""
    all_ev = db.fetch_evidence()
    all_products = [dict(r) for r in db.fetch_all()]
    matched_candidate_count = sum(
        1 for p in all_products
        if _match_evidence_to_candidate(all_ev, p.get("name", ""))
    )
    ev_stats = db.fetch_evidence_stats()
    return {
        "ok": True,
        "storage": "sqlite",
        "evidence_ready_for_scoring": True,
        "external_connections_enabled": False,
        "credentials_required": False,
        "total_evidence_count": ev_stats["total"],
        "active_evidence_count": ev_stats["active"],
        "accepted_evidence_count": ev_stats["accepted"],
        "weak_evidence_count": ev_stats["weak"],
        "rejected_evidence_count": ev_stats["rejected"],
        "duplicate_evidence_count": ev_stats["duplicate"],
        "matched_candidate_count": matched_candidate_count,
        "allowed_sources": sorted(_ALLOWED_EVIDENCE_SOURCES),
        "allowed_signal_types": sorted(_ALLOWED_SIGNAL_TYPES),
        "latest_observed_at_utc": db.latest_evidence_observed_at(),
    }
