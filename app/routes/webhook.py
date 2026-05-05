"""
PayFast Instant Transaction Notification (ITN) webhook.

PayFast posts to this endpoint after a payment completes. We verify the
notification is authentic (signature + server-side validation), then unlock
the corresponding scan tier.

Every ITN — successful or not — is audit-logged to the `payments` table.
This is important for debugging signature mismatches, refund disputes, and
PayFast support queries.

PayFast ITN docs: https://developers.payfast.co.za/docs#step_3_verify_the_payment
"""

import os
from typing import Optional

import httpx
from fastapi import APIRouter, Request, HTTPException

from app.db import upgrade_scan_tier, log_payment
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

    # Pull out everything we need for logging up-front, before any potential
    # exception. This way every ITN is logged — even rejected ones.
    pf_payment_id = payload.get("pf_payment_id") or payload.get("m_payment_id") or "unknown"
    scan_id = payload.get("custom_str1")
    tier_str = payload.get("custom_int1")
    tier: Optional[int] = int(tier_str) if tier_str and tier_str.isdigit() else None

    # ----- Step 1: Verify the signature -----
    received_signature = payload.pop("signature", None)
    expected_signature = _payfast_signature(payload, PAYFAST_PASSPHRASE)
    signature_valid = received_signature == expected_signature

    if not signature_valid:
        print(f"[webhook] PayFast signature mismatch: got {received_signature}, "
              f"expected {expected_signature}")
        await _audit_log(
            pf_payment_id=pf_payment_id,
            payload=payload,
            scan_id=scan_id,
            tier=tier,
            signature_valid=False,
            server_validated=False,
        )
        raise HTTPException(status_code=400, detail="Bad signature.")

    # Re-add the signature for server validation step
    payload["signature"] = received_signature

    # ----- Step 2: Server-to-server validation with PayFast -----
    server_validated = await _server_validate(payload)

    if not server_validated:
        await _audit_log(
            pf_payment_id=pf_payment_id,
            payload=payload,
            scan_id=scan_id,
            tier=tier,
            signature_valid=True,
            server_validated=False,
        )
        raise HTTPException(status_code=400, detail="Server validation failed.")

    # Always log the (now-verified) ITN — even non-COMPLETE statuses,
    # since we want a record of every payment lifecycle event.
    await _audit_log(
        pf_payment_id=pf_payment_id,
        payload=payload,
        scan_id=scan_id,
        tier=tier,
        signature_valid=True,
        server_validated=True,
    )

    # ----- Step 3: Confirm payment status -----
    if payload.get("payment_status") != "COMPLETE":
        # Pending / cancelled / failed — logged above, no further action.
        return {"status": "ignored", "reason": payload.get("payment_status")}

    # ----- Step 4: Unlock the scan tier -----
    if not scan_id or tier is None:
        raise HTTPException(status_code=422, detail="Missing scan or tier metadata.")

    upgraded = await upgrade_scan_tier(scan_id, tier=tier, payment_id=pf_payment_id)
    if not upgraded:
        print(f"[webhook] No scan matched ITN for scan_id={scan_id}")
        raise HTTPException(status_code=404, detail="Scan not found.")

    # Tier 3 (rewrite) — notify the operator. For v1 just a print + the
    # rewrite_intake table will be checked manually. Future: Slack webhook
    # or email.
    if tier == 3:
        print(f"[webhook] NEW REWRITE PAYMENT: scan_id={scan_id} pf_id={pf_payment_id}")

    return {"status": "ok", "scan_id": scan_id, "tier": tier}


# ---------- Internal helpers ----------

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


async def _audit_log(
    pf_payment_id: str,
    payload: dict,
    scan_id: Optional[str],
    tier: Optional[int],
    signature_valid: bool,
    server_validated: bool,
) -> None:
    """Write the ITN to the audit table. Never raises — log-and-swallow."""
    try:
        await log_payment(
            pf_payment_id=pf_payment_id,
            scan_id=scan_id,
            tier=tier,
            amount_gross=payload.get("amount_gross", ""),
            amount_fee=payload.get("amount_fee", ""),
            amount_net=payload.get("amount_net", ""),
            payment_status=payload.get("payment_status", ""),
            signature_valid=signature_valid,
            server_validated=server_validated,
            raw_payload=payload,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[webhook] audit log write failed: {exc}")
