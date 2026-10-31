"""Passwords, login tokens and access checks.

Identity and role always come from the verified token, never from the request body.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from . import config, db
from .errors import ApiError, forbidden, not_found, unauthenticated

ROLES = ("recruiter", "hiring_manager", "hr_admin", "auditor")
READ_ALL_ROLES = ("auditor", "hr_admin")


# --- passwords (scrypt, stdlib) -------------------------------------------
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt_b64, dk_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:
        return False


# --- tokens ---------------------------------------------------------------
def issue_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=config.TOKEN_MINUTES)
    return jwt.encode({"sub": user_id, "exp": exp}, config.JWT_SECRET, algorithm="HS256")


def current_user(request) -> dict:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise unauthenticated()
    try:
        claims = jwt.decode(auth[7:].strip(), config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise unauthenticated()
    row = db.one("SELECT id, email, name, role FROM users WHERE id=?", (claims.get("sub"),))
    if not row:
        raise unauthenticated()
    return dict(row)


# --- scope ----------------------------------------------------------------
def is_member(user: dict, case_id: str) -> bool:
    return db.one("SELECT 1 FROM case_members WHERE case_id=? AND user_id=?", (case_id, user["id"])) is not None


def require_case_read(user: dict, case_id: str) -> dict:
    case = db.one("SELECT * FROM cases WHERE id=?", (case_id,))
    if not case or not (user["role"] in READ_ALL_ROLES or is_member(user, case_id)):
        raise not_found("Case")
    return dict(case)


def require_case_write(user: dict, case_id: str, roles=("recruiter",)) -> dict:
    case = require_case_read(user, case_id)
    if not is_member(user, case_id):
        raise forbidden("READ_ONLY", "You can read this case but not change it.")
    if user["role"] not in roles:
        raise forbidden("FORBIDDEN_ROLE", f"This action needs the role: {', '.join(roles)}.")
    return case


def require_role(user: dict, *roles: str) -> None:
    if user["role"] not in roles:
        raise forbidden("FORBIDDEN_ROLE", f"This action needs the role: {', '.join(roles)}.")


def case_of(table: str, obj_id: str, what: str) -> str:
    row = db.one(f"SELECT case_id FROM {table} WHERE id=?", (obj_id,))
    if not row:
        raise not_found(what)
    return row["case_id"]


def ensure(cond: bool, err: ApiError) -> None:
    if not cond:
        raise err
