"""
Scan route — handles CV upload, parsing, scoring, and result delivery.

Flow:
1. User uploads CV (PDF or DOCX) + optional job description + email
2. Backend extracts plain text from the CV
3. Hands off to the scoring engine (`app.scorer.score_cv`)
4. Stores the result in SQLite (so the user can retrieve it later or upgrade)
5. Returns the top-line score + structural issues + missing keywords (free tier)
6. Optionally emails the user a copy via Buttondown integration
"""

import uuid
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.scorer import score_cv
from app.parsers import extract_text_from_cv
from app.db import save_scan
from app.email import send_free_report
from app.models import FreeScanResponse

router = APIRouter()

MAX_FILE_BYTES = 5 * 1024 * 1024  # 5MB
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}


@router.post("/free", response_model=FreeScanResponse)
async def free_scan(
    cv: UploadFile = File(..., description="CV file (PDF or DOCX, <=5MB)"),
    job_description: Optional[str] = Form(
        default=None, description="Job ad text — optional but improves keyword scoring"
    ),
    email: str = Form(..., description="Where to send the report"),
    region: str = Form(default="auto", description="ZA | UK | US | auto"),
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

    if len(cv_text.strip()) < 100:
        raise HTTPException(
            status_code=422,
            detail=(
                "We extracted very little text from this CV. It may be scanned, "
                "image-based, or heavily formatted. ATS systems will struggle "
                "with it for the same reason."
            ),
        )

    # ----- Run the scoring engine -----
    # NOTE: app.scorer.score_cv is where your existing Python ATS scoring tool
    # plugs in. It should accept (cv_text, job_description, region) and return a
    # ScoringResult. See app/scorer.py for the adapter shape.
    result = score_cv(
        cv_text=cv_text,
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

    # ----- Send the free-tier report by email (fire-and-forget) -----
    # Don't block the response on email delivery; if Buttondown is down we still
    # want the user to see their score on screen.
    try:
        await send_free_report(
            email=email,
            score=result.score,
            structural_issues=result.structural_issues[:3],
            missing_keywords=result.missing_keywords[:5],
            scan_id=scan_id,
        )
    except Exception as exc:  # noqa: BLE001 — log and continue
        print(f"[email] free report send failed for scan {scan_id}: {exc}")

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
