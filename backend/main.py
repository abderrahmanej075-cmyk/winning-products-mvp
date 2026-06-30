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


def _build_source_readiness_summary(sources_used: list = None) -> dict:
    """Build a human- and machine-readable source readiness summary.

    Classifies every registered connector into five readiness buckets and
    adds context about which sources are currently powering recommendations.

    sources_used: raw source names from the DB or discovery output (may include
                  stub variants like 'ebay_stub', 'ebay_stub_fallback').
    """
    ready, disabled_s, missing_creds, access_req = [], [], [], []
    for name, connector in CONNECTORS.items():
        st = connector.status
        if st == "active":
            ready.append(name)
        elif st == "disabled":
            disabled_s.append(name)
        elif st == "missing_credentials":
            missing_creds.append(name)
        elif st == "access_required":
            access_req.append(name)
        # "planned" — not yet implemented; listed separately in build_readiness_plan()

    # Degraded: connector is registered active (creds present) but only stub data
    # was returned (live API yielded zero results for all seeds).
    _STUB_INDICATORS = {"ebay_stub", "ebay_stub_fallback"}
    degraded = []
    if sources_used:
        for src in sources_used:
            if src in _STUB_INDICATORS:
                base = src.split("_stub")[0]
                label = f"{base} (stub only — live API returned no results)"
                if label not in degraded:
                    degraded.append(label)

    # Active recommendation sources: normalize raw DB names to readable labels
    _STUB_LABELS = {
        "ebay_stub": "ebay [stub]",
        "ebay_stub_fallback": "ebay [stub fallback]",
    }
    active_rec = []
    for src in (sources_used or []):
        label = _STUB_LABELS.get(src, src)
        if label not in active_rec:
            active_rec.append(label)

    plan = build_readiness_plan()
    next_best = plan["next_sources_to_connect"][0]["name"] if plan["next_sources_to_connect"] else None

    ready_str = ", ".join(ready) if ready else "none"
    if not ready and not active_rec:
        summary_text = (
            "No sources are active. Add products manually or configure eBay credentials."
        )
    elif degraded:
        summary_text = (
            f"Active connectors: {ready_str}. "
            f"Stub data in use — live source returned no results: {', '.join(degraded)}. "
            + (f"Next recommended source: {next_best}." if next_best else "")
        )
    elif next_best:
        summary_text = (
            f"Active connectors: {ready_str}. "
            f"Next recommended source to connect: {next_best}."
        )
    else:
        summary_text = f"All registered sources are active: {ready_str}."

    return {
        "ready_sources": ready,
        "disabled_sources": disabled_s,
        "missing_credentials_sources": missing_creds,
        "access_required_sources": access_req,
        "degraded_sources": degraded,
        "active_recommendation_sources": active_rec,
        "next_best_source_to_connect": next_best,
        "summary_text": summary_text,
    }


def _build_daily_quality_gate(
    top_candidates: list,
    quality_status: str,
    best_rec: str,
    evidence_summary: dict,
    source_readiness_summary: dict,
    avg_score: float = None,
) -> dict:
    """Classify the daily report into a conservative action decision.

    Synthesises product scores, evidence quality, and source readiness into a
    single gate decision. Never modifies candidates or scores — read-only summary.

    decision:   test_small_budget | watchlist | reject | needs_more_evidence
    confidence: high | medium | low
    score:      0–100 meta-score combining product score, evidence, and source depth
    """
    _DECISION_LABELS = {
        "test_small_budget": "Test with Small Budget",
        "watchlist": "Add to Watchlist",
        "reject": "Reject",
        "needs_more_evidence": "Needs More Evidence",
    }
    _REC_ACTIONABLE = {"Strong candidate", "Test with small budget"}

    top = top_candidates[0] if top_candidates else None
    top_score = top.get("score") if top else None
    top_name = top.get("name", "") if top else ""
    active_ev = evidence_summary.get("active_evidence_count", 0)
    accepted_ev = evidence_summary.get("accepted_evidence_count", 0)
    rejected_ev = evidence_summary.get("rejected_evidence_count", 0)
    ready_sources = source_readiness_summary.get("ready_sources", [])
    degraded = source_readiness_summary.get("degraded_sources", [])
    active_rec_srcs = source_readiness_summary.get("active_recommendation_sources", [])

    stub_only = bool(degraded) and not any(
        "[stub" not in s for s in active_rec_srcs
    )

    reasons: list = []
    risks: list = []
    missing_evidence: list = []
    do_not_do: list = []

    # ------------------------------------------------------------------ decision
    if quality_status == "empty" or not top:
        decision = "reject"
        reasons.append("No products in the database.")
        missing_evidence.append(
            "Run /discovery/multisource or POST /discovery/manual to populate candidates."
        )

    elif quality_status == "weak":
        decision = "reject"
        reasons.append("No candidates scored above the Reject threshold.")
        missing_evidence.append(
            "Try different seed keywords with clearer buyer pain points."
        )

    elif best_rec in _REC_ACTIONABLE:
        if accepted_ev == 0:
            # Promising score but zero validated evidence — too uncertain to spend
            decision = "needs_more_evidence"
            reasons.append(
                f"'{top_name}' scores {top_score}/60 ({best_rec}) "
                "but has no accepted market evidence records."
            )
            missing_evidence.append(
                "Add at least one accepted evidence signal via POST /evidence/market-signal."
            )
            missing_evidence.append(
                "Accepted signal types: demand (search interest), trend (direction), "
                "competition (competitor count), supplier (cost estimate)."
            )
        else:
            decision = "test_small_budget"
            reasons.append(
                f"'{top_name}' scores {top_score}/60 with recommendation: {best_rec}."
            )
            reasons.append(
                f"{accepted_ev} accepted evidence record(s) support the signal."
            )

    elif best_rec == "Watchlist":
        decision = "watchlist"
        reasons.append(
            f"'{top_name}' scores {top_score}/60 with recommendation: Watchlist."
        )
        missing_evidence.append(
            "Validate demand signals before committing budget. "
            "Add evidence via POST /evidence/market-signal."
        )

    else:
        decision = "reject"
        reasons.append(f"Best available recommendation is: {best_rec or 'None'}.")

    # ------------------------------------------------------------------ risks
    if stub_only:
        risks.append(
            "Candidates sourced from stub fallback — "
            "live eBay returned no results. Real market fit unconfirmed."
        )
    if active_ev == 0:
        risks.append(
            "No active market evidence. Decision relies on scoring signals only."
        )
    if top_score is not None and top_score < 25:
        risks.append(
            f"Top score is {top_score}/60 — below the 25-point minimum "
            "for reliable test signals."
        )
    if len(ready_sources) <= 1:
        risks.append(
            "Only one active data source. "
            "Connect additional sources to reduce signal uncertainty."
        )
    if rejected_ev > accepted_ev and accepted_ev < 3:
        risks.append(
            "Evidence quality is low — more records rejected than accepted. "
            "Review submitted signals for accuracy."
        )

    # ------------------------------------------------------------------ do_not_do
    if decision in ("reject", "needs_more_evidence"):
        do_not_do.append(
            "Do not spend budget on any candidate in this batch before "
            "the quality gate reaches test_small_budget."
        )
    if stub_only:
        do_not_do.append(
            "Do not treat stub-sourced candidates as confirmed market signals. "
            "Verify demand with live discovery or manual research first."
        )
    if quality_status == "weak":
        do_not_do.append(
            "Do not test any current candidates — all score below the actionable threshold."
        )

    # ------------------------------------------------------------------ gate score (0–100)
    product_pts = (top_score / 60.0 * 50.0) if top_score is not None else 0.0
    evidence_pts = min(1.0, accepted_ev / 5.0) * 30.0
    source_pts = min(1.0, len(ready_sources) / 4.0) * 20.0
    gate_score = round(product_pts + evidence_pts + source_pts)

    # ------------------------------------------------------------------ confidence
    if gate_score >= 70 and active_ev >= 2 and len(risks) == 0:
        confidence = "high"
    elif gate_score >= 40 and quality_status not in ("weak", "empty"):
        confidence = "medium"
    else:
        confidence = "low"

    # ------------------------------------------------------------------ action strings
    _SAFE_ACTIONS: dict = {
        "test_small_budget": (
            f"Order a small test batch of '{top_name}' and validate real conversion "
            "before scaling. Start with one ad creative."
        ) if top else "Run /discovery/multisource to find a candidate.",
        "watchlist": (
            f"Monitor '{top_name}' for 1–2 weeks. "
            "Add demand evidence before committing any budget."
        ) if top else "Add products and rerun the daily report.",
        "reject": (
            "Run /discovery/multisource with new seed keywords "
            "to find better candidates."
        ),
        "needs_more_evidence": (
            "Add at least one accepted evidence signal via POST /evidence/market-signal, "
            "then rerun /reports/daily."
        ),
    }
    _BUDGET_GUIDANCE: dict = {
        "test_small_budget": (
            "Start with $50–$150 on a single product. "
            "Test one ad creative. Measure CTR and conversion before scaling."
        ),
        "watchlist": (
            "Hold budget. Gather evidence for 1–2 weeks and rerun the quality gate."
        ),
        "reject": "Do not allocate budget to this batch. Restart discovery.",
        "needs_more_evidence": (
            "Hold budget until evidence is submitted and the quality gate "
            "reaches test_small_budget."
        ),
    }

    return {
        "decision": decision,
        "decision_label": _DECISION_LABELS.get(decision, decision),
        "confidence": confidence,
        "score": gate_score,
        "reasons": reasons,
        "risks": risks,
        "missing_evidence": missing_evidence,
        "safe_next_action": _SAFE_ACTIONS.get(decision, ""),
        "budget_guidance": _BUDGET_GUIDANCE.get(decision, ""),
        "do_not_do": do_not_do,
    }


def _build_product_decision_card(
    top_candidate: dict = None,
    quality_gate: dict = None,
    evidence_summary: dict = None,
    source_readiness_summary: dict = None,
) -> dict:
    """Summarize the single best recommendation as a human-readable decision card.

    Read-only summary built entirely from already-computed report data
    (quality_gate, evidence_summary, source_readiness_summary, top candidate).
    Never touches scoring and never removes or reorders candidates.
    """
    quality_gate = quality_gate or {}
    evidence_summary = evidence_summary or {}
    source_readiness_summary = source_readiness_summary or {}

    decision = quality_gate.get("decision", "reject")
    decision_label = quality_gate.get("decision_label", "Reject")
    confidence = quality_gate.get("confidence", "low")
    score = quality_gate.get("score", 0)
    next_action = quality_gate.get("safe_next_action", "")
    budget = quality_gate.get("budget_guidance", "")
    risks = list(quality_gate.get("risks", []))
    missing_evidence = list(quality_gate.get("missing_evidence", []))
    why = list(quality_gate.get("reasons", []))

    ready_sources = source_readiness_summary.get("ready_sources", [])
    degraded = source_readiness_summary.get("degraded_sources", [])
    if degraded:
        source_status = f"Degraded — {', '.join(degraded)}"
    elif ready_sources:
        source_status = f"Active: {', '.join(ready_sources)}"
    else:
        source_status = "No active sources"

    # No candidate — return a safe empty card. Decision comes from quality_gate,
    # which already resolves to reject or needs_more_evidence when there is no top.
    if not top_candidate:
        return {
            "product": None,
            "decision": decision,
            "decision_label": decision_label,
            "confidence": confidence,
            "score": score,
            "why": why or ["No product candidate is currently available."],
            "evidence": [],
            "risks": risks,
            "missing_evidence": missing_evidence or [
                "Run /discovery/multisource or POST /discovery/manual to find candidates."
            ],
            "next_action": next_action or "Run /discovery/multisource to find a candidate.",
            "budget": budget or "Do not allocate budget — no candidate to test.",
            "source_status": source_status,
            "one_sentence_summary": (
                "No product candidate available — run discovery before making a decision."
            ),
        }

    product_name = top_candidate.get("name", "Unnamed product")

    # Evidence list — matched market evidence first, then positive scoring reasons
    evidence_items: list = []
    ev_count = top_candidate.get("evidence_count", 0)
    ev_sources = top_candidate.get("evidence_sources") or []
    if ev_count:
        evidence_items.append(
            f"{ev_count} matched market evidence record(s) from: {', '.join(ev_sources) or 'unknown'}."
        )
    conf_avg = top_candidate.get("evidence_confidence_avg")
    if conf_avg is not None:
        evidence_items.append(f"Average evidence confidence: {conf_avg}.")
    for reason in top_candidate.get("positive_reasons", []):
        if reason not in evidence_items:
            evidence_items.append(reason)
    if not evidence_items:
        evidence_items.append("No supporting evidence recorded for this product yet.")

    # Risks — merge gate-level risks with product-level caution/filter reasons
    for reason in top_candidate.get("caution_reasons", []) + top_candidate.get("filter_reasons", []):
        if reason and reason not in risks:
            risks.append(reason)

    if decision == "test_small_budget":
        why = why + [
            "Testing is allowed because the product score, recommendation, and "
            "accepted evidence all clear the conservative bar for a small test."
        ]
        next_action = next_action or (
            f"Run a small controlled test for '{product_name}' — this is not a full launch."
        )
        one_sentence_summary = (
            f"'{product_name}' clears the bar for a small controlled test "
            f"({confidence} confidence, {score}/100) — not a full launch."
        )
    elif decision == "watchlist":
        one_sentence_summary = (
            f"'{product_name}' is promising but needs more validation before any budget is spent."
        )
    elif decision == "needs_more_evidence":
        one_sentence_summary = (
            f"'{product_name}' scores well but lacks accepted market evidence — "
            "add evidence before testing."
        )
    else:
        one_sentence_summary = (
            f"'{product_name}' does not currently meet the bar for testing — reject for now."
        )

    return {
        "product": product_name,
        "decision": decision,
        "decision_label": decision_label,
        "confidence": confidence,
        "score": score,
        "why": why,
        "evidence": evidence_items,
        "risks": risks,
        "missing_evidence": missing_evidence,
        "next_action": next_action,
        "budget": budget,
        "source_status": source_status,
        "one_sentence_summary": one_sentence_summary,
    }


def _build_daily_action_plan(
    product_decision_card: dict = None,
    quality_gate: dict = None,
    evidence_summary: dict = None,
    source_readiness_summary: dict = None,
) -> dict:
    """Build a conservative, test-first operator action plan.

    Read-only summary derived from product_decision_card + quality_gate
    (plus evidence/source context for missing-evidence wording). Never
    touches scoring and never removes or reorders candidates — this only
    explains what a human operator should do next.
    """
    product_decision_card = product_decision_card or {}
    quality_gate = quality_gate or {}
    evidence_summary = evidence_summary or {}
    source_readiness_summary = source_readiness_summary or {}

    decision = quality_gate.get("decision", "reject")
    product_name = product_decision_card.get("product")
    missing_evidence = list(quality_gate.get("missing_evidence", []))
    risks = list(quality_gate.get("risks", []))
    next_best_source = source_readiness_summary.get("next_best_source_to_connect")
    accepted_ev = evidence_summary.get("accepted_evidence_count", 0)

    if not product_name:
        return {
            "today_action": "Run /discovery/multisource (or POST /discovery/manual) to find a candidate.",
            "validation_steps": [
                "Add seed keywords and run discovery.",
                "Review returned candidates once available.",
            ],
            "small_test_budget": "Do not allocate budget — no candidate to test.",
            "test_setup": [],
            "success_criteria": [],
            "stop_conditions": [
                "No candidate found after discovery — do not spend on ads or inventory.",
            ],
            "scale_conditions": [],
            "what_to_avoid": [
                "Do not spend any budget without a scored candidate.",
            ],
            "owner_note": "No product candidate is available yet.",
            "one_sentence_plan": "Run discovery to find a candidate before planning any action.",
        }

    if decision == "test_small_budget":
        today_action = (
            f"Run a small controlled validation test for '{product_name}' — this is NOT a full launch."
        )
        validation_steps = [
            "Confirm supplier cost, shipping time, and margin before spending.",
            "Prepare 1-2 ad creatives or listings for a limited audience/budget.",
            "Launch the small test and monitor results daily.",
        ]
        small_test_budget = "Small, capped test budget only (e.g. a modest daily spend for a few days) — not a full launch budget."
        test_setup = [
            f"List or advertise '{product_name}' to a narrow, limited audience.",
            "Cap total spend in advance and do not exceed it without a review checkpoint.",
            "Track orders, cost per result, and margin from day one.",
        ]
        success_criteria = [
            "Positive or break-even margin after fees and shipping.",
            "Clear buyer interest (orders, click-through, or add-to-cart signal) within the test window.",
        ]
        stop_conditions = [
            "Stop immediately if the small test budget is exhausted with no positive signal.",
            "Stop if margin is negative after fees and shipping.",
            "Stop if no orders or engagement are seen within the agreed test window.",
        ]
        scale_conditions = [
            "Only scale gradually if the small test shows positive margin and repeatable demand.",
            "Re-run /reports/daily after the test to confirm the quality gate still supports scaling.",
            "Do not move to a full launch in a single step — increase budget incrementally.",
        ]
        what_to_avoid = [
            "Do not skip straight to a full launch or large ad budget.",
            "Do not ignore the stop conditions if the test underperforms.",
        ] + risks
        owner_note = (
            f"'{product_name}' has cleared the conservative bar for a small test only. "
            "Treat this as validation, not a green light for full-scale spend."
        )
        one_sentence_plan = (
            f"Run a small, capped test for '{product_name}' with clear stop/scale checkpoints — not a full launch."
        )

    elif decision == "watchlist":
        today_action = f"Add '{product_name}' to the watchlist and continue collecting evidence — do not spend yet."
        validation_steps = [
            "Monitor the product's score and evidence over the next few report runs.",
            "Add any new market evidence (reviews, demand signals, supplier data) as it becomes available.",
        ] + ([f"Connect {next_best_source} for additional signal."] if next_best_source else [])
        small_test_budget = "No budget recommended yet — continue monitoring."
        test_setup = []
        success_criteria = [
            "Score or evidence improves enough to move the quality gate to test_small_budget.",
        ]
        stop_conditions = [
            "Stop monitoring and drop the product if score or evidence trends downward.",
        ]
        scale_conditions = [
            "Re-evaluate once additional accepted evidence is recorded or the score improves.",
        ]
        what_to_avoid = [
            "Do not spend ad or inventory budget while still on the watchlist.",
        ] + risks
        owner_note = f"'{product_name}' is promising but not yet validated — keep watching, do not spend."
        one_sentence_plan = f"Keep '{product_name}' on the watchlist and gather more evidence before any spend."

    elif decision == "needs_more_evidence":
        today_action = f"Collect specific validation evidence for '{product_name}' before any spend."
        validation_steps = (
            missing_evidence
            or [
                "Submit supporting market evidence via the evidence intake endpoint.",
                "Look for independent demand, review, or social-proof signals for this product.",
            ]
        )
        small_test_budget = "No budget yet — evidence must be collected first."
        test_setup = []
        success_criteria = [
            "At least one piece of accepted, active evidence is recorded for this product.",
        ]
        stop_conditions = [
            "Do not spend any budget until accepted evidence exists.",
        ]
        scale_conditions = [
            "Once accepted evidence is recorded, re-run /reports/daily — the gate may move to test_small_budget.",
        ]
        what_to_avoid = [
            "Do not test or spend budget based on score alone without supporting evidence.",
        ] + risks
        owner_note = (
            f"'{product_name}' scores well but lacks accepted evidence "
            f"({accepted_ev} accepted so far) — validate before testing."
        )
        one_sentence_plan = f"Gather specific validation evidence for '{product_name}' before considering any spend."

    else:  # reject
        today_action = f"Do not spend any budget on '{product_name}' — reject for now."
        validation_steps = [
            "Look for a different candidate via /discovery/multisource.",
            "Revisit this product only if its score, recommendation, or evidence materially improve.",
        ]
        small_test_budget = "No budget — this product is rejected."
        test_setup = []
        success_criteria = []
        stop_conditions = [
            "Do not list, advertise, or order inventory for this product.",
        ]
        scale_conditions = []
        what_to_avoid = [
            "Do not spend any budget on this product in its current state.",
        ] + risks
        owner_note = f"'{product_name}' does not currently meet the bar for testing."
        one_sentence_plan = f"Reject '{product_name}' for now and look for a stronger candidate."

    return {
        "today_action": today_action,
        "validation_steps": validation_steps,
        "small_test_budget": small_test_budget,
        "test_setup": test_setup,
        "success_criteria": success_criteria,
        "stop_conditions": stop_conditions,
        "scale_conditions": scale_conditions,
        "what_to_avoid": what_to_avoid,
        "owner_note": owner_note,
        "one_sentence_plan": one_sentence_plan,
    }


def _build_operator_daily_brief(
    product_decision_card: dict = None,
    quality_gate: dict = None,
    action_plan: dict = None,
    evidence_summary: dict = None,
    source_readiness_summary: dict = None,
) -> dict:
    """Build a short, plain-language daily brief for a non-technical operator.

    Read-only summary combining product_decision_card, quality_gate, action_plan,
    evidence_summary, and source_readiness_summary. Never touches scoring and
    never removes or reorders candidates.
    """
    product_decision_card = product_decision_card or {}
    quality_gate = quality_gate or {}
    action_plan = action_plan or {}
    evidence_summary = evidence_summary or {}
    source_readiness_summary = source_readiness_summary or {}

    decision = quality_gate.get("decision", "reject")
    confidence = quality_gate.get("confidence", "low")
    product_name = product_decision_card.get("product")
    today_action = action_plan.get("today_action", "")
    budget = action_plan.get("small_test_budget") or product_decision_card.get("budget", "")
    stop_if = list(action_plan.get("stop_conditions", []))
    scale_if = list(action_plan.get("scale_conditions", []))
    missing_evidence = list(quality_gate.get("missing_evidence", []))

    ready_sources = source_readiness_summary.get("ready_sources", [])
    degraded = source_readiness_summary.get("degraded_sources", [])
    if degraded:
        sources_status = f"Degraded — running on stub data for: {', '.join(degraded)}."
    elif ready_sources:
        sources_status = f"Active sources: {', '.join(ready_sources)}."
    else:
        sources_status = "No active sources yet."

    title = "Winning Products — Daily Operator Brief"

    if not product_name:
        plain_text = (
            f"{title}\n"
            "No product candidate is available today. Run discovery to find one "
            "before making any spending decision.\n"
            f"Sources: {sources_status}"
        )
        return {
            "title": title,
            "today_product": None,
            "decision": decision,
            "confidence": confidence,
            "why_this_matters": "There is no scored candidate to evaluate today.",
            "today_action": today_action or "Run /discovery/multisource to find a candidate.",
            "budget": "No budget — there is nothing to test yet.",
            "stop_if": stop_if or ["No candidate found — do not spend on ads or inventory."],
            "scale_if": scale_if,
            "sources_status": sources_status,
            "missing_before_scaling": missing_evidence or [
                "A scored product candidate from discovery."
            ],
            "plain_text": plain_text,
        }

    if decision == "test_small_budget":
        why_this_matters = (
            f"'{product_name}' has cleared the conservative bar for a small controlled "
            "test only — it is not a full launch."
        )
        headline = f"Today: run a small controlled test only for '{product_name}'. This is NOT a full launch."
    elif decision == "watchlist":
        why_this_matters = (
            f"'{product_name}' looks promising but has not yet cleared the bar for spending. "
            "Monitor it and collect more evidence."
        )
        headline = f"Today: monitor '{product_name}' and collect more evidence — no spend yet."
    elif decision == "needs_more_evidence":
        why_this_matters = (
            f"'{product_name}' scores well but lacks the supporting evidence needed before any spend."
        )
        headline = f"Today: validate '{product_name}' with more evidence before spending anything."
    else:
        why_this_matters = (
            f"'{product_name}' does not currently meet the bar for testing or spending."
        )
        headline = f"Today: no spend on '{product_name}'. Reject for now."

    plain_text = (
        f"{title}\n"
        f"{headline}\n"
        f"Confidence: {confidence}\n"
        f"Budget: {budget}\n"
        f"Sources: {sources_status}\n"
    )
    if stop_if:
        plain_text += "Stop if: " + "; ".join(stop_if) + "\n"
    if scale_if:
        plain_text += "Scale if: " + "; ".join(scale_if) + "\n"

    return {
        "title": title,
        "today_product": product_name,
        "decision": decision,
        "confidence": confidence,
        "why_this_matters": why_this_matters,
        "today_action": today_action or headline,
        "budget": budget,
        "stop_if": stop_if,
        "scale_if": scale_if,
        "sources_status": sources_status,
        "missing_before_scaling": missing_evidence,
        "plain_text": plain_text,
    }


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

    source_readiness_summary = _build_source_readiness_summary(sources_used)
    quality_gate = _build_daily_quality_gate(
        top_candidates=top_candidates,
        quality_status=quality_status,
        best_rec=best_rec,
        evidence_summary=evidence_summary,
        source_readiness_summary=source_readiness_summary,
        avg_score=avg,
    )
    product_decision_card = _build_product_decision_card(
        top_candidate=top_candidates[0] if top_candidates else None,
        quality_gate=quality_gate,
        evidence_summary=evidence_summary,
        source_readiness_summary=source_readiness_summary,
    )
    daily_action_plan = _build_daily_action_plan(
        product_decision_card=product_decision_card,
        quality_gate=quality_gate,
        evidence_summary=evidence_summary,
        source_readiness_summary=source_readiness_summary,
    )
    operator_daily_brief = _build_operator_daily_brief(
        product_decision_card=product_decision_card,
        quality_gate=quality_gate,
        action_plan=daily_action_plan,
        evidence_summary=evidence_summary,
        source_readiness_summary=source_readiness_summary,
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
        "source_readiness_summary": source_readiness_summary,
        "quality_gate": quality_gate,
        "product_decision_card": product_decision_card,
        "action_plan": daily_action_plan,
        "operator_daily_brief": operator_daily_brief,
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
    source_readiness_summary = report.get("source_readiness_summary", {})
    quality_gate = report.get("quality_gate", {})
    product_decision_card = report.get("product_decision_card", {})
    daily_action_plan = report.get("action_plan", {})
    operator_daily_brief = report.get("operator_daily_brief", {})

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
        "quality_gate": {
            "decision": quality_gate.get("decision"),
            "decision_label": quality_gate.get("decision_label"),
            "confidence": quality_gate.get("confidence"),
            "score": quality_gate.get("score"),
            "safe_next_action": quality_gate.get("safe_next_action"),
            "budget_guidance": quality_gate.get("budget_guidance"),
        },
        "product_decision_card": {
            "product": product_decision_card.get("product"),
            "decision": product_decision_card.get("decision"),
            "decision_label": product_decision_card.get("decision_label"),
            "confidence": product_decision_card.get("confidence"),
            "score": product_decision_card.get("score"),
            "next_action": product_decision_card.get("next_action"),
            "budget": product_decision_card.get("budget"),
            "one_sentence_summary": product_decision_card.get("one_sentence_summary"),
        },
        "action_plan": {
            "today_action": daily_action_plan.get("today_action"),
            "small_test_budget": daily_action_plan.get("small_test_budget"),
            "stop_conditions": daily_action_plan.get("stop_conditions"),
            "scale_conditions": daily_action_plan.get("scale_conditions"),
            "one_sentence_plan": daily_action_plan.get("one_sentence_plan"),
        },
        "operator_daily_brief_text": operator_daily_brief.get("plain_text"),
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
        "payload_version": "2G-K",
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
        "source_readiness_summary": source_readiness_summary,
        "quality_gate": quality_gate,
        "product_decision_card": product_decision_card,
        "action_plan": daily_action_plan,
        "operator_daily_brief": operator_daily_brief,
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
        ebay_connector = CONNECTORS.get("ebay")
        ebay_status = ebay_connector.status if ebay_connector else "missing_credentials"
        has_live_ebay = ebay_status == "ready"
        ebay_env = (
            settings.ebay_env if settings.ebay_env in ("sandbox", "production") else "sandbox"
        )

        if not has_live_ebay:
            missing_sources.append({
                "source": "ebay_live",
                "note": (
                    f"eBay live mode not active (status: {ebay_status}). "
                    + (ebay_connector.readiness_reason(ebay_status) if ebay_connector else "")
                    + " Using eBay stub data instead — no live eBay data is included."
                ),
            })

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
            # build_collector() selects production vs sandbox credentials based on
            # the connector's active environment — never EbayCollector() bare here,
            # which would always default to sandbox credentials regardless of status.
            collector = ebay_connector.build_collector()
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
