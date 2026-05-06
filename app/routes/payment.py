"""
PayFast checkout flow.

Creates the redirect URL that sends the user to PayFast's hosted checkout for
Tier 2 (R99 diagnostic report) or Tier 3 (R450+ rewrite). PayFast posts back
to /api/webhook/payfast — see app/routes/webhook.py.

PayFast docs: https://developers.payfast.co.za/docs#process_url
"""

import hashlib
import os
import urllib.parse
from typing import Literal

from fastapi import APIRouter, HTTPException

from app.db import get_scan

router = APIRouter()

PAYFAST_MERCHANT_ID = os.environ.get("PAYFAST_MERCHANT_ID", "")
PAYFAST_MERCHANT_KEY = os.environ.get("PAYFAST_MERCHANT_KEY", "")
PAYFAST_PASSPHRASE = os.environ.get("PAYFAST_PASSPHRASE", "")
PAYFAST_SANDBOX = os.environ.get("PAYFAST_SANDBOX", "true").lower() == "true"
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://cited.co.za")

PROCESS_URL_LIVE = "https://www.payfast.co.za/eng/process"
PROCESS_URL_SANDBOX = "https://sandbox.payfast.co.za/eng/process"

# Tier definitions. Keep these in sync with the landing-page pricing.
TIERS = {
    "diagnostic": {
        "amount": "99.00",
        "item_name": "Cited Full Diagnostic Report",
        "tier_id": 2,
    },
    "rewrite_basic": {
        "amount": "450.00",
        "item_name": "Cited CV Rewrite — Standard",
        "tier_id": 3,
    },
    "rewrite_premium": {
        "amount": "950.00",
        "item_name": "Cited CV Rewrite — Premium",
        "tier_id": 3,
    },
}

TierKey = Literal["diagnostic", "rewrite_basic", "rewrite_premium"]


@router.post("/checkout/{tier}")
async def create_checkout(tier: TierKey, scan_id: str):
    """
    Generate PayFast checkout payload for upgrading a scan.

    Returns the form fields and the action URL — the frontend then submits
    a hidden HTML form via POST. PayFast strongly prefers POST over GET
    redirects (the sandbox can reject GET with a 400). PayFast will redirect
    back to {PUBLIC_BASE_URL}/upgrade/return?scan={scan_id} on success and
    post an ITN to /api/webhook/payfast for confirmation.
    """
    if tier not in TIERS:
        raise HTTPException(status_code=404, detail="Unknown tier.")

    if not PAYFAST_MERCHANT_ID or not PAYFAST_MERCHANT_KEY:
        raise HTTPException(
            status_code=500,
            detail="PayFast is not configured. Set PAYFAST_MERCHANT_ID and PAYFAST_MERCHANT_KEY.",
        )

    scan = await get_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found.")

    tier_config = TIERS[tier]

    # name_first must be alphabetic and at least 2 characters. PayFast
    # rejects single-character or empty first names. Email local parts
    # are stripped to alpha-only; if too short, fall back to "Customer".
    raw_name = scan.get("email", "").split("@")[0]
    alpha_only = "".join(c for c in raw_name if c.isalpha())[:50]
    safe_name = alpha_only if len(alpha_only) >= 2 else "Customer"

    # Lowercase the email — PayFast may normalise case, which would
    # cause a signature mismatch if we send the original-case version.
    email_normalised = scan["email"].strip().lower()

    fields = {
        "merchant_id": PAYFAST_MERCHANT_ID,
        "merchant_key": PAYFAST_MERCHANT_KEY,
        "return_url": f"{PUBLIC_BASE_URL}/upgrade/return?scan={scan_id}",
        "cancel_url": f"{PUBLIC_BASE_URL}/upgrade/cancel?scan={scan_id}",
        "notify_url": f"{PUBLIC_BASE_URL}/api/webhook/payfast",
        "name_first": safe_name,
        "name_last": "Customer",   # PayFast often requires both name_first and name_last
        "email_address": email_normalised,
        "m_payment_id": f"{scan_id}:{tier}",   # so we can recover the scan on ITN
        "amount": tier_config["amount"],
        "item_name": tier_config["item_name"],
        "custom_str1": scan_id,
        "custom_int1": str(tier_config["tier_id"]),
    }

    fields["signature"] = _payfast_signature(fields, PAYFAST_PASSPHRASE)

    action_url = PROCESS_URL_SANDBOX if PAYFAST_SANDBOX else PROCESS_URL_LIVE

    return {
        "action_url": action_url,
        "fields": fields,
    }


def _payfast_signature(fields: dict, passphrase: str) -> str:
    """
    Compute the PayFast MD5 signature.

    PayFast spec (developers.payfast.co.za/docs#step_2_signature, yellow box):
    fields must be in the order they are sent in the POST/URL, NOT alphabetical.
    Python dicts preserve insertion order since 3.7 so we just iterate.

    Empty values are excluded. Signature itself is excluded. Values are
    URL-encoded with PHP-style encoding (spaces as +). Passphrase, if set,
    appended at the end as &passphrase=...
    """
    payload_parts = []
    for key, value in fields.items():
        if key == "signature":
            continue
        if value == "" or value is None:
            continue
        payload_parts.append(f"{key}={urllib.parse.quote_plus(str(value))}")
    payload = "&".join(payload_parts)
    if passphrase:
        payload += f"&passphrase={urllib.parse.quote_plus(passphrase)}"
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


@router.get("/debug/{tier}")
async def debug_checkout(tier: TierKey, scan_id: str):
    """
    Return the exact signature payload for a checkout attempt.

    Sandbox-only. Lets us see what we're hashing, what hash we're producing,
    and whether the passphrase is wired in. Visit this endpoint manually in
    the browser to diagnose signature mismatches without going through the
    PayFast UI.
    """
    if not PAYFAST_SANDBOX:
        raise HTTPException(status_code=403, detail="Debug endpoint disabled outside sandbox.")

    if tier not in TIERS:
        raise HTTPException(status_code=404, detail="Unknown tier.")

    scan = await get_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found.")

    tier_config = TIERS[tier]
    raw_name = scan.get("email", "").split("@")[0]
    alpha_only = "".join(c for c in raw_name if c.isalpha())[:50]
    safe_name = alpha_only if len(alpha_only) >= 2 else "Customer"
    email_normalised = scan["email"].strip().lower()

    fields = {
        "merchant_id": PAYFAST_MERCHANT_ID,
        "merchant_key": PAYFAST_MERCHANT_KEY,
        "return_url": f"{PUBLIC_BASE_URL}/upgrade/return?scan={scan_id}",
        "cancel_url": f"{PUBLIC_BASE_URL}/upgrade/cancel?scan={scan_id}",
        "notify_url": f"{PUBLIC_BASE_URL}/api/webhook/payfast",
        "name_first": safe_name,
        "name_last": "Customer",
        "email_address": email_normalised,
        "m_payment_id": f"{scan_id}:{tier}",
        "amount": tier_config["amount"],
        "item_name": tier_config["item_name"],
        "custom_str1": scan_id,
        "custom_int1": str(tier_config["tier_id"]),
    }

    # Build the payload string exactly as we hash it
    payload_parts = []
    for key, value in fields.items():
        if value == "" or value is None:
            continue
        payload_parts.append(f"{key}={urllib.parse.quote_plus(str(value))}")
    payload = "&".join(payload_parts)
    payload_with_passphrase = payload
    if PAYFAST_PASSPHRASE:
        payload_with_passphrase = payload + f"&passphrase={urllib.parse.quote_plus(PAYFAST_PASSPHRASE)}"

    sig_no_passphrase = hashlib.md5(payload.encode("utf-8")).hexdigest()
    sig_with_passphrase = hashlib.md5(payload_with_passphrase.encode("utf-8")).hexdigest()

    return {
        "merchant_id_set": bool(PAYFAST_MERCHANT_ID),
        "merchant_key_set": bool(PAYFAST_MERCHANT_KEY),
        "passphrase_set": bool(PAYFAST_PASSPHRASE),
        "passphrase_length": len(PAYFAST_PASSPHRASE) if PAYFAST_PASSPHRASE else 0,
        "fields_in_order": list(fields.keys()),
        "payload_no_passphrase": payload,
        "payload_with_passphrase": payload_with_passphrase if PAYFAST_PASSPHRASE else "(passphrase not set)",
        "signature_no_passphrase": sig_no_passphrase,
        "signature_with_passphrase": sig_with_passphrase if PAYFAST_PASSPHRASE else "(passphrase not set)",
        "signature_being_sent": sig_with_passphrase if PAYFAST_PASSPHRASE else sig_no_passphrase,
    }
