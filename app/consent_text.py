"""
Marketing consent text — versioned and hashed.

POPIA requires consent records to be auditable: we must be able to show, for
any past consent grant, the exact text the user saw at the time. Storing the
text version + a SHA256 hash of the text alongside each grant gives us that.

If you change the text, bump CURRENT_VERSION. The hash is computed from the
text live, so it stays consistent automatically.
"""

import hashlib

CURRENT_VERSION = "v1-2026-05-04"

CURRENT_TEXT = (
    "Email me CV tips and tool updates from Cited. "
    "About one email per month, no spam. Unsubscribe anytime in one click."
)


def current_text_hash() -> str:
    """SHA256 hash of the current consent text (hex digest)."""
    return hashlib.sha256(CURRENT_TEXT.encode("utf-8")).hexdigest()


# Required-consent text (storage of CV) — recorded for completeness but not
# treated as marketing consent.
STORAGE_CONSENT_TEXT = (
    "I'm OK with Cited storing my CV for 30 days so I can retrieve or "
    "upgrade my report. After 30 days it's permanently deleted."
)
