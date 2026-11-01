"""Recipient confirmation (HI-04, decision D11; fixes ground-truth G7).

The email address found in a CV is text the candidate controls, so it is only a SUGGESTION.
A recruiter on the case must confirm the address before any proposal can be created, and the
gateway re-checks at execution that the recipient is exactly the confirmed address.
The ledger records that a confirmation happened and a hash of the address, never the address.
"""
from __future__ import annotations

import re

from . import db, ledger
from .canonical import sha256_hex
from .errors import ApiError, not_found
from .security import require_case_read, require_case_write

# One plain address: no display name, no angle brackets, no separators, no whitespace or
# control characters (blocks CR/LF header injection and comma/semicolon multi-recipient tricks).
_ADDRESS = re.compile(r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63})+")


def clean_address(value: str) -> str:
    """Return the address if it is exactly one safe address, else raise 422."""
    if not isinstance(value, str) or len(value) > 254 or not _ADDRESS.fullmatch(value):
        raise ApiError(422, "RECIPIENT_INVALID",
                       "The recipient must be exactly one email address (no names, separators or line breaks).")
    return value


def _candidate(cand_id: str):
    c = db.one("SELECT * FROM candidates WHERE id=?", (cand_id,))
    if not c:
        raise not_found("Candidate")
    return c


def confirmed_email(cand_id: str) -> str | None:
    row = db.one("SELECT email FROM contact_confirmations WHERE candidate_id=?", (cand_id,))
    return row["email"] if row else None


def get_contact(user: dict, cand_id: str) -> dict:
    c = _candidate(cand_id)
    require_case_write(user, c["case_id"])        # contact data: recruiters on the case only
    suggested = c["contact_email"]
    placeholder = suggested.endswith("@candidates.example.invalid")
    row = db.one("SELECT * FROM contact_confirmations WHERE candidate_id=?", (cand_id,))
    return {"candidate_id": cand_id, "suggested_email": suggested,
            "source": "placeholder" if placeholder else "cv_text",
            "confirmed_email": row["email"] if row else None,
            "confirmed_by": row["confirmed_by"] if row else None,
            "confirmed_at": row["confirmed_at"] if row else None,
            "statement": "The address in a CV is written by the candidate. Check it before confirming."}


def confirm(user: dict, cand_id: str, email: str) -> dict:
    c = _candidate(cand_id)
    require_case_read(user, c["case_id"])
    require_case_write(user, c["case_id"], roles=("recruiter",))
    email = clean_address(email)
    ts = db.now()
    with db.tx() as conn:
        conn.execute("INSERT INTO contact_confirmations VALUES (?,?,?,?) ON CONFLICT(candidate_id) DO UPDATE SET "
                     "email=excluded.email, confirmed_by=excluded.confirmed_by, confirmed_at=excluded.confirmed_at",
                     (cand_id, email, user["id"], ts))
        ledger.append(conn, user["id"], "CONTACT_CONFIRMED", c["case_id"], cand_id,
                      {"email_sha256": sha256_hex(email.lower()),
                       "matches_cv_suggestion": email.lower() == c["contact_email"].lower()})
    return get_contact(user, cand_id)
