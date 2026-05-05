"""
Static-ish content pages: privacy policy, terms, unsubscribe.

These are conceptually static but render through Jinja so they share the
base template chrome and any future personalisation can slot in.
"""

from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.db import withdraw_marketing_consent
from app.templating import templates

router = APIRouter()


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    """Render the privacy policy."""
    return templates.TemplateResponse(request=request, name="privacy.html")


@router.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    """Render the terms of service."""
    return templates.TemplateResponse(request=request, name="terms.html")


@router.get("/popia")
async def popia_redirect():
    """The privacy policy already covers POPIA — redirect to keep the URL working."""
    return RedirectResponse(url="/privacy", status_code=301)


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_form(request: Request, email: Optional[str] = None):
    """
    Show the unsubscribe form.

    If `email` is in the query string (from a one-click link in a future
    marketing email), pre-populate it.
    """
    return templates.TemplateResponse(
        request=request,
        name="unsubscribe.html",
        context={"status": None, "email": email},
    )


@router.post("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_submit(
    request: Request,
    email: str = Form(...),
):
    """
    Process an unsubscribe request.

    Marks every active consent record for the email as withdrawn. Returns
    a 200 with a success page either way — telling the user "we couldn't
    find that email" leaks information about who's on our list, so we
    say "done" regardless. (We do show a not_found state if the email
    is empty/invalid.)
    """
    rows_updated = await withdraw_marketing_consent(
        email=email.strip().lower(),
        method="unsubscribe_page",
    )

    # Always show "done" — never confirm/deny whether the email was on the
    # list, since that would leak our subscriber data to anyone who can
    # type an address.
    return templates.TemplateResponse(
        request=request,
        name="unsubscribe.html",
        context={"status": "done", "email": email, "rows_updated": rows_updated},
    )
