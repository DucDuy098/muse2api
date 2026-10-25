"""Session-cookie auth + RBAC for the team web UI. Fully separate from the
bearer-key `auth()` dependency in app.py, which keeps guarding /v1/* for
programmatic clients untouched.
"""
from __future__ import annotations

import hashlib
import hmac
import os

from fastapi import Cookie, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config import CFG

SESSION_COOKIE_NAME = "m2a_session"
SESSION_MAX_AGE = 7 * 86400  # 7 days

ROLE_RANK = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}

_PBKDF2_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = encoded.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    return hmac.compare_digest(actual, expected)


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(CFG.session_secret, salt="m2a-session")


def make_session_cookie(uid: int, username: str, role: str) -> str:
    return _serializer().dumps({"uid": uid, "u": username, "role": role})


def read_session_cookie(token: str) -> dict | None:
    try:
        return _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def get_current_user(m2a_session: str | None = Cookie(default=None)) -> dict | None:
    """FastAPI dependency: decoded session dict, or None if not logged in.
    Does not raise — routes that allow anonymous access use this directly;
    routes that require login use `require_role` instead."""
    if not m2a_session:
        return None
    return read_session_cookie(m2a_session)


def require_role(min_role: str):
    """Returns a dependency raising 401 (no session) or 403 (role too low),
    else the decoded user dict. Mirrors app.py's auth() pattern."""
    min_rank = ROLE_RANK[min_role]

    def _check(user: dict | None = None) -> dict:
        if user is None:
            raise HTTPException(401, "Chưa đăng nhập")
        if ROLE_RANK.get(user.get("role"), -1) < min_rank:
            raise HTTPException(403, f"Cần quyền tối thiểu '{min_role}'")
        return user

    def _dependency(m2a_session: str | None = Cookie(default=None)) -> dict:
        return _check(get_current_user(m2a_session))

    return _dependency
