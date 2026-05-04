"""
Email delivery — Buttondown integration.

The free-tier scan emails the user a copy of their results. This serves three
purposes:
1. Recovery — they don't lose the report when they close the tab.
2. Email capture — Buttondown is the newsletter pipeline for upsells.
3. Trust — receiving a clean, branded email is part of the credibility signal.

If BUTTONDOWN_API_KEY isn't set, this module degrades silently. The user still
sees their score on screen — they just don't get an email copy. Useful in dev.
"""

import os
from typing import List

import httpx

from app.models import StructuralIssue


BUTTONDOWN_API_KEY = os.environ.get("BUTTONDOWN_API_KEY")
BUTTONDOWN_BASE = "https://api.buttondown.email/v1"


async def send_free_report(
    email: str,
    score: int,
    structural_issues: List[StructuralIssue],
    missing_keywords: List[str],
    scan_id: str,
) -> bool:
    """
    Send the free-tier report to the user.

    Two things happen:
    1. The user is added to the Buttondown subscriber list (with consent — see
       the consent checkbox in the upload form).
    2. A transactional-style email is sent with their results.

    Returns True on success, False on any failure. Failures are logged but do
    not propagate — the on-screen result is the primary delivery channel.
    """
    if not BUTTONDOWN_API_KEY:
        print("[email] BUTTONDOWN_API_KEY not set — skipping email delivery")
        return False

    headers = {
        "Authorization": f"Token {BUTTONDOWN_API_KEY}",
        "Content-Type": "application/json",
    }

    # 1. Subscribe the user (idempotent — Buttondown ignores duplicates).
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{BUTTONDOWN_BASE}/subscribers",
                headers=headers,
                json={
                    "email_address": email,
                    "tags": ["cited-free-scan"],
                    "metadata": {"latest_scan_id": scan_id, "latest_score": str(score)},
                },
            )
    except Exception as exc:  # noqa: BLE001
        print(f"[email] subscriber upsert failed: {exc}")

    # 2. Send the actual report email.
    issues_html = "".join(
        f"<li><strong>{issue.severity.upper()}:</strong> {issue.description}</li>"
        for issue in structural_issues
    ) or "<li>No critical structural issues detected.</li>"

    keywords_html = "".join(
        f"<li>{kw}</li>" for kw in missing_keywords
    ) or "<li>No specific keyword gaps to flag (no job ad provided).</li>"

    email_body = f"""<h1>Your Cited ATS Score: {score}/100</h1>

<p>Here are the headline findings from your scan. The full diagnostic report
(line-by-line annotations, complete keyword gap analysis, region-tuned fix
guide) is available for R99 — that's the next step if you want detail.</p>

<h2>Top structural issues</h2>
<ul>{issues_html}</ul>

<h2>Missing keywords</h2>
<ul>{keywords_html}</ul>

<p><a href="https://cited.co.za/upgrade?scan={scan_id}">Get the full diagnostic
report — R99</a></p>

<p>— The Cited Team</p>"""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{BUTTONDOWN_BASE}/emails",
                headers=headers,
                json={
                    "subject": f"Your Cited ATS score: {score}/100",
                    "body": email_body,
                    "email_type": "private",
                    "to": [email],
                },
            )
            response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"[email] free report send failed: {exc}")
        return False

    return True
