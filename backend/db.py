"""SQLite data layer (Python stdlib only — no ORM, no external deps).

Stores one row per product with the V2 scoring-spec input fields. Any field left
NULL is treated by the scoring engine as 'Not Measured' (excluded from the score
denominator, counted against confidence).
"""
import json
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "products.db")

# Every writable column (id and created_at handled separately).
ALLCOLS = [
    "name", "category", "country", "created_at",
    # demand
    "trends_interest", "amazon_bsr", "reddit_posts_90d", "pinterest_saves",
    # trend growth
    "trends_direction_pct", "seasonality_ratio", "tiktok_momentum",
    # profit inputs
    "supplier_cost", "shipping_cost", "retail_price", "product_weight_kg",
    # content
    "tiktok_hashtag_views", "meta_active_advertisers", "meta_ad_longevity_days", "demo_videos_top10",
    # competition
    "aliexpress_sellers_1k", "brand_dominance_pct", "competitor_count",
    # differentiation
    "diff_unaddressed_themes", "diff_complement_skus", "diff_oem_available",
    "diff_market_fragmented", "diff_organic_ugc",
    # elimination-filter inputs
    "legal_restricted", "hazmat", "fragile_material", "breakage_mentions",
    "longest_dim_cm", "seasonality_offpeak", "alltime_current_value",
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            source TEXT NOT NULL,
            country TEXT NOT NULL DEFAULT 'US',
            signal_type TEXT NOT NULL,
            value TEXT,
            confidence REAL,
            notes TEXT,
            observed_at_utc TEXT,
            created_at_utc TEXT NOT NULL,
            quality_status TEXT DEFAULT 'accepted',
            quality_score REAL DEFAULT 100,
            quality_reasons TEXT DEFAULT '[]',
            duplicate_of INTEGER,
            is_active INTEGER DEFAULT 1
        )
        """
    )
    # Migrate existing market_evidence tables — idempotent, each ALTER is try/excepted
    for _col_def in [
        "ADD COLUMN quality_status TEXT DEFAULT 'accepted'",
        "ADD COLUMN quality_score REAL DEFAULT 100",
        "ADD COLUMN quality_reasons TEXT DEFAULT '[]'",
        "ADD COLUMN duplicate_of INTEGER",
        "ADD COLUMN is_active INTEGER DEFAULT 1",
    ]:
        try:
            conn.execute(f"ALTER TABLE market_evidence {_col_def}")
        except Exception:
            pass
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            country TEXT DEFAULT 'US',
            created_at TEXT,
            trends_interest INTEGER,
            amazon_bsr INTEGER,
            reddit_posts_90d INTEGER,
            pinterest_saves INTEGER,
            trends_direction_pct REAL,
            seasonality_ratio REAL,
            tiktok_momentum TEXT,
            supplier_cost REAL,
            shipping_cost REAL,
            retail_price REAL,
            product_weight_kg REAL,
            tiktok_hashtag_views INTEGER,
            meta_active_advertisers INTEGER,
            meta_ad_longevity_days INTEGER,
            demo_videos_top10 INTEGER,
            aliexpress_sellers_1k INTEGER,
            brand_dominance_pct REAL,
            competitor_count INTEGER,
            diff_unaddressed_themes INTEGER,
            diff_complement_skus INTEGER,
            diff_oem_available INTEGER,
            diff_market_fragmented INTEGER,
            diff_organic_ugc INTEGER,
            legal_restricted INTEGER,
            hazmat INTEGER,
            fragile_material INTEGER,
            breakage_mentions INTEGER,
            longest_dim_cm REAL,
            seasonality_offpeak INTEGER,
            alltime_current_value INTEGER
        )
        """
    )
    # Migrate products table — add discovery-specific columns (idempotent)
    for _prod_col in [
        "ADD COLUMN source TEXT",
        "ADD COLUMN source_url TEXT",
        "ADD COLUMN score REAL",
        "ADD COLUMN recommendation TEXT",
        "ADD COLUMN discovered_at TEXT",
        "ADD COLUMN shortlisted INTEGER DEFAULT 0",
        "ADD COLUMN shortlisted_at TEXT",
        "ADD COLUMN review_status TEXT DEFAULT 'new'",
        "ADD COLUMN operator_notes TEXT",
        "ADD COLUMN reviewed_at TEXT",
    ]:
        try:
            conn.execute(f"ALTER TABLE products {_prod_col}")
        except Exception:
            pass
    conn.commit()
    conn.close()


def _parse_evidence_row(row) -> dict:
    """Return a market_evidence row as a clean dict with typed quality fields."""
    d = dict(row)
    raw_qr = d.get("quality_reasons")
    try:
        d["quality_reasons"] = json.loads(raw_qr) if raw_qr else []
    except Exception:
        d["quality_reasons"] = []
    is_active_raw = d.get("is_active")
    d["is_active"] = bool(is_active_raw) if is_active_raw is not None else True
    d["quality_status"] = d.get("quality_status") or "accepted"
    q_score = d.get("quality_score")
    d["quality_score"] = float(q_score) if q_score is not None else 100.0
    d["duplicate_of"] = d.get("duplicate_of")
    return d


def insert_product(d):
    d = dict(d)
    d.setdefault("country", "US")
    if not d.get("created_at"):
        d["created_at"] = now_iso()
    keys = [k for k in d.keys() if k in ALLCOLS and d[k] is not None]
    placeholders = ",".join(["?"] * len(keys))
    sql = f"INSERT INTO products ({','.join(keys)}) VALUES ({placeholders})"
    conn = get_conn()
    cur = conn.execute(sql, [d[k] for k in keys])
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def fetch_all():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM products ORDER BY id").fetchall()
    conn.close()
    return rows


def fetch_by_id(pid):
    conn = get_conn()
    row = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    conn.close()
    return row


def insert_evidence(data: dict, quality: dict = None, duplicate_of: int = None) -> dict:
    """Insert one market evidence record with quality metadata."""
    quality = quality or {"quality_status": "accepted", "quality_score": 100.0, "quality_reasons": [], "is_active": True}
    created_at = now_iso()
    value_str = str(data["value"]) if data.get("value") is not None else None
    quality_reasons_json = json.dumps(quality.get("quality_reasons") or [])
    is_active_int = 1 if quality.get("is_active", True) else 0
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO market_evidence
           (product_name, source, country, signal_type, value, confidence, notes,
            observed_at_utc, created_at_utc, quality_status, quality_score,
            quality_reasons, duplicate_of, is_active)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["product_name"],
            data["source"],
            data.get("country") or "US",
            data["signal_type"],
            value_str,
            data.get("confidence"),
            data.get("notes"),
            data.get("observed_at_utc"),
            created_at,
            quality.get("quality_status", "accepted"),
            quality.get("quality_score", 100.0),
            quality_reasons_json,
            duplicate_of,
            is_active_int,
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return {
        "id": row_id,
        "product_name": data["product_name"],
        "source": data["source"],
        "country": data.get("country") or "US",
        "signal_type": data["signal_type"],
        "value": value_str,
        "confidence": data.get("confidence"),
        "notes": data.get("notes"),
        "observed_at_utc": data.get("observed_at_utc"),
        "created_at_utc": created_at,
        "quality_status": quality.get("quality_status", "accepted"),
        "quality_score": quality.get("quality_score", 100.0),
        "quality_reasons": quality.get("quality_reasons") or [],
        "duplicate_of": duplicate_of,
        "is_active": quality.get("is_active", True),
    }


def fetch_evidence(
    product_name: str = None,
    source: str = None,
    signal_type: str = None,
    country: str = None,
) -> list:
    """Return matching market_evidence rows as a list of dicts, newest first."""
    clauses, params = [], []
    if product_name:
        clauses.append("TRIM(LOWER(product_name)) = ?")
        params.append(product_name.strip().lower())
    if source:
        clauses.append("source = ?")
        params.append(source)
    if signal_type:
        clauses.append("signal_type = ?")
        params.append(signal_type)
    if country:
        clauses.append("UPPER(TRIM(country)) = ?")
        params.append(country.strip().upper())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    conn = get_conn()
    rows = conn.execute(
        f"SELECT * FROM market_evidence {where} ORDER BY created_at_utc DESC",
        params,
    ).fetchall()
    conn.close()
    return [_parse_evidence_row(r) for r in rows]


def count_evidence() -> int:
    """Return the total number of market evidence records."""
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM market_evidence").fetchone()[0]
    conn.close()
    return n


def fetch_evidence_sources() -> list:
    """Return sorted list of distinct sources from active market_evidence records."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT source FROM market_evidence WHERE is_active = 1 OR is_active IS NULL ORDER BY source"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def find_duplicate_evidence(
    product_name: str, source: str, country: str, signal_type: str, value
) -> int:
    """Return the id of an existing active evidence record with the same key fields, or None."""
    value_str = str(value) if value is not None else None
    conn = get_conn()
    row = conn.execute(
        """SELECT id FROM market_evidence
           WHERE TRIM(LOWER(product_name)) = ?
           AND source = ?
           AND UPPER(TRIM(country)) = ?
           AND signal_type = ?
           AND ((value = ?) OR (? IS NULL AND value IS NULL))
           AND (is_active = 1 OR is_active IS NULL)
           LIMIT 1""",
        (
            product_name.strip().lower(),
            source,
            (country or "US").strip().upper(),
            signal_type,
            value_str,
            value_str,
        ),
    ).fetchone()
    conn.close()
    return row[0] if row else None


def fetch_evidence_stats() -> dict:
    """Return evidence counts grouped by quality_status, plus total and active counts."""
    conn = get_conn()
    status_rows = conn.execute(
        "SELECT quality_status, COUNT(*) FROM market_evidence GROUP BY quality_status"
    ).fetchall()
    active_count = conn.execute(
        "SELECT COUNT(*) FROM market_evidence WHERE is_active = 1 OR is_active IS NULL"
    ).fetchone()[0]
    conn.close()
    counts: dict = {}
    for status, cnt in status_rows:
        counts[status or "accepted"] = cnt
    total = sum(counts.values())
    return {
        "total": total,
        "active": active_count,
        "accepted": counts.get("accepted", 0),
        "weak": counts.get("weak", 0),
        "rejected": counts.get("rejected", 0),
        "duplicate": counts.get("duplicate", 0),
    }


def latest_evidence_observed_at():
    """Return the most recent observed_at_utc across all evidence records, or None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT observed_at_utc FROM market_evidence ORDER BY created_at_utc DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row[0] if row else None


def fetch_by_name_country(name: str, country: str):
    normalized_name = name.strip().lower()
    normalized_country = (country or "US").strip().upper()
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM products WHERE TRIM(LOWER(name)) = ? AND UPPER(TRIM(country)) = ?",
        (normalized_name, normalized_country),
    ).fetchone()
    conn.close()
    return row


import re as _re


def _normalize_name_for_dedup(name: str) -> str:
    """Lowercase, trim, collapse whitespace, strip simple punctuation — for DB dedup only."""
    t = (name or "").lower().strip()
    t = _re.sub(r"[^\w\s]", "", t)
    t = _re.sub(r"\s+", " ", t).strip()
    return t


def upsert_discovered_candidate(candidate: dict) -> dict:
    """Persist one discovered candidate into the products table, skipping true duplicates.

    Dedup priority (same source first):
      1. source + source_url  — exact URL match
      2. source + item_id     — exact item-id match (when populated)
      3. source + normalized name — lowercased, punctuation-stripped title match

    Returns a dict with:
      inserted  bool — True if a new row was created
      id        int  — row id (existing or new)
      reason    str  — 'inserted' | 'duplicate_url' | 'duplicate_item_id' | 'duplicate_title'
    """
    source = (candidate.get("source") or "").strip()
    source_url = (candidate.get("source_url") or "").strip() or None
    item_id = (candidate.get("item_id") or "").strip() or None
    name = (candidate.get("name") or "").strip()
    country = (candidate.get("country") or "US").strip().upper()

    conn = get_conn()

    # 1. Dedup by source + source_url
    if source_url:
        row = conn.execute(
            "SELECT id FROM products WHERE source = ? AND source_url = ? LIMIT 1",
            (source, source_url),
        ).fetchone()
        if row:
            conn.close()
            return {"inserted": False, "id": row[0], "reason": "duplicate_url"}

    # 2. Dedup by source + item_id
    if item_id:
        row = conn.execute(
            "SELECT id FROM products WHERE source = ? AND item_id = ? LIMIT 1",
            (source, item_id),
        ).fetchone()
        if row:
            conn.close()
            return {"inserted": False, "id": row[0], "reason": "duplicate_item_id"}

    # 3. Dedup by source + normalized name
    norm_name = _normalize_name_for_dedup(name)
    if norm_name:
        row = conn.execute(
            "SELECT id FROM products WHERE source = ? AND TRIM(LOWER(name)) = ? LIMIT 1",
            (source, norm_name),
        ).fetchone()
        if row:
            conn.close()
            return {"inserted": False, "id": row[0], "reason": "duplicate_title"}

    # Not a duplicate — insert
    discovered_at = candidate.get("discovered_at") or now_iso()
    retail_price = candidate.get("retail_price")
    score_val = candidate.get("score")
    recommendation = candidate.get("recommendation")

    cur = conn.execute(
        """INSERT INTO products (name, category, country, source, source_url,
               retail_price, score, recommendation, discovered_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            name,
            candidate.get("category") or "other",
            country,
            source or None,
            source_url,
            retail_price,
            score_val,
            recommendation,
            discovered_at,
            discovered_at,
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"inserted": True, "id": new_id, "reason": "inserted"}


def toggle_shortlist(pid: int) -> dict:
    """Toggle the shortlisted flag for a product row.

    Returns the new state: {"id": int, "shortlisted": bool, "shortlisted_at": str|None}
    Raises ValueError if the product does not exist.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT id, shortlisted, shortlisted_at FROM products WHERE id = ?", (pid,)
    ).fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"Product {pid} not found")

    currently = bool(row["shortlisted"])
    if currently:
        conn.execute(
            "UPDATE products SET shortlisted = 0, shortlisted_at = NULL WHERE id = ?", (pid,)
        )
        new_flag, new_at = False, None
    else:
        new_at = now_iso()
        conn.execute(
            "UPDATE products SET shortlisted = 1, shortlisted_at = ? WHERE id = ?", (new_at, pid)
        )
        new_flag = True

    conn.commit()
    conn.close()
    return {"id": pid, "shortlisted": new_flag, "shortlisted_at": new_at}


ALLOWED_REVIEW_STATUSES = frozenset({"new", "researching", "test_candidate", "rejected", "winner"})


def update_review_fields(pid: int, review_status: str = None, operator_notes: str = None) -> dict:
    """Update review_status and/or operator_notes for a product.

    At least one of review_status or operator_notes must be provided.
    review_status must be one of ALLOWED_REVIEW_STATUSES.
    Raises ValueError for unknown product or invalid status.
    Returns the updated row's review fields.
    """
    if review_status is not None and review_status not in ALLOWED_REVIEW_STATUSES:
        raise ValueError(
            f"Invalid review_status '{review_status}'. "
            f"Allowed: {sorted(ALLOWED_REVIEW_STATUSES)}"
        )

    conn = get_conn()
    row = conn.execute("SELECT id FROM products WHERE id = ?", (pid,)).fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"Product {pid} not found")

    sets, params = [], []
    if review_status is not None:
        sets.append("review_status = ?")
        params.append(review_status)
    if operator_notes is not None:
        sets.append("operator_notes = ?")
        params.append(operator_notes)

    if not sets:
        conn.close()
        raise ValueError("Provide at least one of review_status or operator_notes")

    reviewed_at = now_iso()
    sets.append("reviewed_at = ?")
    params.append(reviewed_at)
    params.append(pid)

    conn.execute(f"UPDATE products SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()

    updated = conn.execute(
        "SELECT review_status, operator_notes, reviewed_at FROM products WHERE id = ?", (pid,)
    ).fetchone()
    conn.close()
    return {
        "id": pid,
        "review_status": updated["review_status"],
        "operator_notes": updated["operator_notes"],
        "reviewed_at": updated["reviewed_at"],
    }
