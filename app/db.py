"""
SQLite persistence layer.

Single-file database stored in ./data/cited.db. Chosen over Supabase for v1
because it's zero-config on Replit and matches Andrew's stated preference for
single-file, no-build-step technical implementations.

When traffic justifies it, swap this module for a Supabase Postgres client —
the call sites only depend on the async functions defined here, so the
migration is contained.
"""

import json
from pathlib import Path
from typing import Optional

import aiosqlite

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "cited.db"


async def init_db() -> None:
    """Create tables on first run. Idempotent."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS scans (
                scan_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                cv_text TEXT NOT NULL,
                job_description TEXT,
                region TEXT,
                score INTEGER,
                full_result TEXT,                  -- JSON-encoded ScoringResult
                tier INTEGER NOT NULL DEFAULT 1,   -- 1 free, 2 R99 diagnostic, 3 R450+ rewrite
                payment_id TEXT,                   -- PayFast m_payment_id once paid
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_scans_email ON scans(email)"
        )
        await db.commit()


async def save_scan(
    scan_id: str,
    email: str,
    cv_text: str,
    job_description: Optional[str],
    region: str,
    score: int,
    full_result: dict,
) -> None:
    """Persist a scan record."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO scans (scan_id, email, cv_text, job_description, region,
                               score, full_result, tier)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (scan_id, email, cv_text, job_description, region, score,
             json.dumps(full_result)),
        )
        await db.commit()


async def get_scan(scan_id: str) -> Optional[dict]:
    """Fetch a scan by ID. Returns None if not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM scans WHERE scan_id = ?", (scan_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if not row:
        return None
    record = dict(row)
    # Decode the JSON blob so the caller doesn't have to.
    if record.get("full_result"):
        record["full_result"] = json.loads(record["full_result"])
    return record


async def upgrade_scan_tier(scan_id: str, tier: int, payment_id: str) -> bool:
    """Mark a scan as upgraded after PayFast confirms the payment."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE scans SET tier = ?, payment_id = ? WHERE scan_id = ?",
            (tier, payment_id, scan_id),
        )
        await db.commit()
        return cursor.rowcount > 0
