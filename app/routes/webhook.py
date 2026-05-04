"""
PayFast Instant Transaction Notification (ITN) webhook.

PayFast posts to this endpoint after a payment completes. We verify the
notification is authentic (signature + source IP + amount match), then unlock
the corresponding scan tier.

PayFast ITN docs: https://developers.payfast.co.za/docs#step_3_verify_the_payment
"""

import os
from typing import Optional

import httpx
from fastapi import APIRouter, Request, HTTPException

from app.db import upgrade_scan_tier
from app.routes.payment import _payfast_signature

router = APIRouter()

PAYFAST_PASSPHRASE = os.environ.get("PAYFAST_PASSPHRASE", "")
PAYFAST_SANDBOX = os.environ.get("PAYFAST_SANDBOX", "true").lower() == "true"

VALIDATE_URL_LIVE = "https://www.payfast.co.za/eng/query/validate"
VALIDATE_URL_SANDBOX = "https://sandbox.payfast.co.za/eng/query/validate"


@router.post("/payfast")
async def payfast_itn(request: Request):
    """
    Receive PayFast ITN, verify, and unlock the scan tier.

    PayFast sends form-encoded data, not JSON.
    """
    form = await request.form()
    payload = {key: form.get(key) for key in form.keys()}

    # ----- Step 1: Verify the signature -----
    received_signature = payload.pop("signature", None)
    expected_signature = _payfast_signature(payload, PAYFAST_PASSPHRASE)
    if received_signature != expected_signature:
        # Signature failures are common during testing — log loudly so they're
        # easy to find in Replit's deployment logs.
        print(f"[webhook] PayFast signature mismatch: got {received_signature}, "
              f"expected {expected_signature}")
        raise HTTPException(status_code=400, detail="Bad signature.")

    # ----- Step 2: Server-to-server validation with PayFast -----
    # This guards against someone forging an ITN with a stolen passphrase.
    payload["signature"] = received_signature
    if not await _server_validate(payload):
        raise HTTPException(status_code=400, detail="Server validation failed.")

    # ----- Step 3: Confirm payment status -----
    if payload.get("payment_status") != "COMPLETE":
        # Not an error — just a status we don't act on yet.
        return {"status": "ignored", "reason": payload.get("payment_status")}

    # ----- Step 4: Unlock the scan tier -----
    scan_id = payload.get("custom_str1")
    tier_str = payload.get("custom_int1")
    payment_id = payload.get("pf_payment_id") or payload.get("m_payment_id")

    if not scan_id or not tier_str:
        raise HTTPException(status_code=422, detail="Missing scan or tier metadata.")

    try:
        tier = int(tier_str)
    except ValueError:
        raise HTTPException(status_code=422, detail="Bad tier value.")

    upgraded = await upgrade_scan_tier(scan_id, tier=tier, payment_id=payment_id or "")
    if not upgraded:
        # Scan ID didn't match any record — possibly already processed, possibly fraud.
        print(f"[webhook] No scan matched ITN for scan_id={scan_id}")
        raise HTTPException(status_code=404, detail="Scan not found.")

    # If tier == 3 (rewrite), here's where you'd kick off the manual workflow:
    # send yourself a notification, queue a task, etc. For v1 a Buttondown
    # notification email or even a Slack webhook is fine.

    return {"status": "ok", "scan_id": scan_id, "tier": tier}


async def _server_validate(payload: dict) -> bool:
    """
    Re-post the ITN payload to PayFast for server-side validation.

    PayFast returns plain text "VALID" or "INVALID".
    """
    url = VALIDATE_URL_SANDBOX if PAYFAST_SANDBOX else VALIDATE_URL_LIVE
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, data=payload)
            response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"[webhook] server validation error: {exc}")
        return False
    return response.text.strip().upper() == "VALID"
