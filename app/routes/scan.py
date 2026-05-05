"""
Scan route — handles CV upload, parsing, scoring, and result delivery.

Flow:
1. User uploads CV (PDF or DOCX) + optional job description + email
2. Backend extracts plain text from the CV
3. Hands off to the scoring engine (`app.scorer.score_cv`)
4. Stores the result in SQLite (so the user can retrieve it later or upgrade)
5. Returns the top-line score + structural issues + missing keywords (free tier)

The email field is captured but not used for sending in v1 — it serves as
the unique identifier for the scan record. If/when the upsell sequence is
built, this is where the addresses come from.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.scorer import score_cv
from app.parsers import extract_text_from_cv
from app.db import save_scan, record_marketing_consent
from app.models import FreeScanResponse
from app.consent_text import CURRENT_VERSION, current_text_hash

router = APIRouter()

MAX_FILE_BYTES = 5 * 1024 * 1024  # 5MB
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}


@router.post("/free", response_model=FreeScanResponse)
async def free_scan(
    request: Request,
    cv: UploadFile = File(..., description="CV file (PDF or DOCX, <=5MB)"),
    job_description: Optional[str] = Form(
        default=None, description="Job ad text — optional but improves keyword scoring"
    ),
    email: str = Form(..., description="Email — used to retrieve the scan later"),
    region: str = Form(default="auto", description="ZA | UK | US | auto"),
    marketing_consent: bool = Form(
        default=False,
        description=(
            "True if the user explicitly opted in to marketing emails. "
            "Default False — POPIA requires affirmative opt-in."
        ),
    ),
):
    """
    Free Tier 1 scan: returns top-line score + 3 structural errors + 5 missing keywords.

    The full diagnostic (line-by-line annotations, complete gap analysis, fix guide)
    is gated behind the R99 Tier 2 upgrade — see /api/payment/checkout/diagnostic.
    """
    # ----- Validate upload -----
    if cv.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail="CV must be a PDF or Word document.",
        )

    cv_bytes = await cv.read()
    if len(cv_bytes) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="CV file is larger than 5MB. Please compress or simplify.",
        )

    if not email or "@" not in email:
        raise HTTPException(
            status_code=422,
            detail="A valid email address is required.",
        )

    # ----- Extract plain text from the upload -----
    try:
        cv_text = extract_text_from_cv(cv_bytes, cv.content_type)
    except Exception as exc:
        # Parsing failures are themselves a useful ATS signal — flag this to the user.
        raise HTTPException(
            status_code=422,
            detail=(
                "We couldn't parse this CV. That's actually significant — it means "
                "an ATS probably can't either. Try saving as a plain PDF without "
                "embedded images or text boxes, then re-upload."
            ),
        ) from exc

    if len(cv_text.strip()) < 50:
        # Truly tiny extractions are still rejected outright — the user gets
        # nothing meaningful from a 5-character score. But anything above 50
        # chars now gets scored honestly (low score with explicit issues),
        # which is more useful than a refusal.
        raise HTTPException(
            status_code=422,
            detail=(
                "We extracted almost no text from this CV. It's likely a scanned "
                "image or so heavily formatted that nothing parses. ATS systems "
                "will fail on it for the same reason — please save as a plain "
                "PDF without embedded images and re-upload."
            ),
        )

    # ----- Run the scoring engine -----
    # The scorer needs raw bytes + content type to do full parseability
    # analysis (re-parsing the PDF to detect tables, images, multi-column
    # layouts that text-only inspection can't see).
    result = score_cv(
        cv_text=cv_text,
        raw_bytes=cv_bytes,
        content_type=cv.content_type,
        job_description=job_description or "",
        region=region,
    )

    # ----- Persist for later retrieval / upgrade -----
    scan_id = str(uuid.uuid4())
    await save_scan(
        scan_id=scan_id,
        email=email,
        cv_text=cv_text,
        job_description=job_description,
        region=result.region,
        score=result.score,
        full_result=result.model_dump(),
    )

    # ----- Record marketing consent if granted -----
    # Only record if the user actually ticked the box. POPIA requires the
    # consent to be specific, separate, and freely given — pre-checking the
    # box would void it. The audit trail captures the version of the text
    # they saw, the IP, and the user agent, so the consent is independently
    # provable later.
    if marketing_consent:
        try:
            await record_marketing_consent(
                consent_id=str(uuid.uuid4()),
                email=email,
                consent_text_version=CURRENT_VERSION,
                consent_text_hash=current_text_hash(),
                source="free_scan_form",
                ip_address=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
        except Exception as exc:  # noqa: BLE001
            # Consent failure shouldn't block the scan response — log it
            # so it can be reconciled, but the user still gets their score.
            print(f"[consent] failed to record consent for {email}: {exc}")

    # ----- Return the free-tier subset to the frontend -----
    return FreeScanResponse(
        scan_id=scan_id,
        score=result.score,
        region=result.region,
        rejection_estimate=result.rejection_estimate,
        structural_issues=result.structural_issues[:3],
        missing_keywords=result.missing_keywords[:5],
        upgrade_url=f"/upgrade?scan={scan_id}",
    )


@router.get("/{scan_id}")
async def retrieve_scan(scan_id: str):
    """
    Retrieve a previously-run scan.

    Used after PayFast confirms payment — the frontend redirects here to render
    the unlocked Tier 2 (R99) full diagnostic report.
    """
    from app.db import get_scan  # local import to avoid circular deps at top level

    scan = await get_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found or expired.")
    return scan


# ---------- helpers ----------

def _client_ip(request: Request) -> Optional[str]:
    """
    Extract the real client IP, accounting for Replit's load balancer.

    The first hop in X-Forwarded-For is the original client. We don't trust
    arbitrary X-Forwarded-For values from the public internet, but Replit's
    proxy populates it correctly.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # First entry is the original client; subsequent entries are proxies
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
