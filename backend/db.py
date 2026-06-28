"""SQLite data layer (Python stdlib only — no ORM, no external deps).

Stores one row per product with the V2 scoring-spec input fields. Any field left
NULL is treated by the scoring engine as 'Not Measured' (excluded from the score
denominator, counted against confidence).
"""
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
            created_at_utc TEXT NOT NULL
        )
        """
    )
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
    conn.commit()
    conn.close()


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


def insert_evidence(data: dict) -> dict:
    """Insert one market evidence record and return it with id and created_at_utc."""
    created_at = now_iso()
    value_str = str(data["value"]) if data.get("value") is not None else None
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO market_evidence
           (product_name, source, country, signal_type, value, confidence, notes,
            observed_at_utc, created_at_utc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
    return [dict(r) for r in rows]


def count_evidence() -> int:
    """Return the total number of market evidence records."""
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM market_evidence").fetchone()[0]
    conn.close()
    return n


def fetch_evidence_sources() -> list:
    """Return sorted list of distinct sources present in market_evidence."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT source FROM market_evidence ORDER BY source"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


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
