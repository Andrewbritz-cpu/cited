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

        # Rewrite intake — collected after the user pays for Tier 3.
        # The actual rewrite is done by you (or your editor) outside the system.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS rewrite_intake (
                intake_id TEXT PRIMARY KEY,
                scan_id TEXT NOT NULL,
                target_role TEXT,
                target_industry TEXT,
                years_experience TEXT,
                key_achievements TEXT,
                preferred_style TEXT,
                additional_notes TEXT,
                phone TEXT,
                status TEXT NOT NULL DEFAULT 'submitted',  -- submitted / in_progress / delivered
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (scan_id) REFERENCES scans(scan_id)
            )
            """
        )

        # Audit trail for every PayFast ITN we receive — successful or not.
        # Critical for debugging signature mismatches, refunds, disputes.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                pf_payment_id TEXT PRIMARY KEY,
                scan_id TEXT,
                tier INTEGER,
                amount_gross TEXT,
                amount_fee TEXT,
                amount_net TEXT,
                payment_status TEXT,
                signature_valid INTEGER,
                server_validated INTEGER,
                raw_payload TEXT,                  -- full JSON of the ITN
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Marketing consent register — POPIA requires consent records to be
        # auditable: who consented, when, what they were told, and from where.
        # We never delete these records (only mark them withdrawn); the audit
        # trail outlives the underlying email address.
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS marketing_consent (
                consent_id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                consent_text_version TEXT NOT NULL,    -- e.g. "v1-2026-05-04"
                consent_text_hash TEXT NOT NULL,       -- SHA256 of the exact text shown
                source TEXT NOT NULL,                  -- "free_scan_form" | "checkout" | "manual"
                ip_address TEXT,
                user_agent TEXT,
                granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                withdrawn_at TIMESTAMP,                -- NULL while active
                withdrawal_method TEXT                 -- "unsubscribe_link" | "email_request" etc
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_marketing_consent_email "
            "ON marketing_consent(email)"
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


async def save_rewrite_intake(
    intake_id: str,
    scan_id: str,
    target_role: str,
    target_industry: str,
    years_experience: str,
    key_achievements: str,
    preferred_style: str,
    additional_notes: str,
    phone: str,
) -> None:
    """Store Tier 3 rewrite intake data after the user pays."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO rewrite_intake (
                intake_id, scan_id, target_role, target_industry,
                years_experience, key_achievements, preferred_style,
                additional_notes, phone
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (intake_id, scan_id, target_role, target_industry,
             years_experience, key_achievements, preferred_style,
             additional_notes, phone),
        )
        await db.commit()


async def get_rewrite_intake(scan_id: str) -> Optional[dict]:
    """Check whether a scan has a rewrite intake record yet."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM rewrite_intake WHERE scan_id = ? LIMIT 1",
            (scan_id,),
        ) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None


async def log_payment(
    pf_payment_id: str,
    scan_id: Optional[str],
    tier: Optional[int],
    amount_gross: str,
    amount_fee: str,
    amount_net: str,
    payment_status: str,
    signature_valid: bool,
    server_validated: bool,
    raw_payload: dict,
) -> None:
    """Audit-log every PayFast ITN, regardless of validation outcome."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO payments (
                pf_payment_id, scan_id, tier, amount_gross, amount_fee,
                amount_net, payment_status, signature_valid,
                server_validated, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (pf_payment_id, scan_id, tier, amount_gross, amount_fee,
             amount_net, payment_status, int(signature_valid),
             int(server_validated), json.dumps(raw_payload)),
        )
        await db.commit()


async def record_marketing_consent(
    consent_id: str,
    email: str,
    consent_text_version: str,
    consent_text_hash: str,
    source: str,
    ip_address: Optional[str],
    user_agent: Optional[str],
) -> None:
    """
    Record a marketing-consent grant.

    Per POPIA, we capture who, when, what (consent_text_hash), and from
    where (IP, user agent) — so the consent is auditable independently of
    the running form code, which may change.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO marketing_consent
                (consent_id, email, consent_text_version, consent_text_hash,
                 source, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (consent_id, email, consent_text_version, consent_text_hash,
             source, ip_address, user_agent),
        )
        await db.commit()


async def withdraw_marketing_consent(email: str, method: str) -> int:
    """
    Mark all active consent records for an email as withdrawn.

    Returns the number of records updated. We never DELETE — POPIA requires
    keeping the audit trail of withdrawal as well as grant.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            UPDATE marketing_consent
            SET withdrawn_at = CURRENT_TIMESTAMP, withdrawal_method = ?
            WHERE email = ? AND withdrawn_at IS NULL
            """,
            (method, email),
        )
        await db.commit()
        return cursor.rowcount


async def has_active_consent(email: str) -> bool:
    """Check whether an email has any non-withdrawn consent on file."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT 1 FROM marketing_consent
            WHERE email = ? AND withdrawn_at IS NULL
            LIMIT 1
            """,
            (email,),
        ) as cursor:
            return await cursor.fetchone() is not None
