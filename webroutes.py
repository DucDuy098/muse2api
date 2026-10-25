"""Login/logout/me + user CRUD for the team web UI. Separate APIRouter so
app.py only needs `app.include_router(router)` — no circular import with
app.py (this module never imports it back)."""
from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel

import db
import webauth

router = APIRouter()


def _require_db():
    if db.POOL is None:
        raise HTTPException(503, "Chưa cấu hình Postgres (MUSE2API_DB_URL) — tính năng tài khoản chưa dùng được")
    return db.POOL


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


class LoginBody(BaseModel):
    username: str
    password: str


class CreateUserBody(BaseModel):
    username: str
    password: str
    role: str


class UpdateUserBody(BaseModel):
    role: str | None = None
    enabled: bool | None = None


def _public_user(row) -> dict:
    return {"id": row["id"], "username": row["username"], "role": row["role"],
            "enabled": row["enabled"], "created_at": row["created_at"].isoformat(),
            "last_login_at": row["last_login_at"].isoformat() if row["last_login_at"] else None}


@router.post("/auth/login")
async def login(body: LoginBody, request: Request, response: Response):
    pool = _require_db()
    ip = _client_ip(request)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, username, password_hash, role, enabled FROM users WHERE username = $1",
            body.username)
        if not row or not row["enabled"] or not webauth.verify_password(body.password, row["password_hash"]):
            await db.audit("login_failed", None, target=body.username, ip=ip)
            raise HTTPException(401, "Sai tên đăng nhập hoặc mật khẩu")
        await conn.execute("UPDATE users SET last_login_at = now() WHERE id = $1", row["id"])
    token = webauth.make_session_cookie(row["id"], row["username"], row["role"])
    # Browsers never send a Secure cookie back over plain HTTP — a dev/sslip.io
    # deploy without TLS yet would set the cookie on login and then silently
    # drop it on every request after. Traefik terminates TLS and talks plain
    # HTTP to this container, so detect the original scheme from its header
    # instead of hardcoding secure=True.
    is_https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(webauth.SESSION_COOKIE_NAME, token, httponly=True, samesite="lax",
                        secure=is_https, max_age=webauth.SESSION_MAX_AGE, path="/")
    user = {"uid": row["id"], "u": row["username"]}
    await db.audit("login", user, ip=ip)
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


@router.post("/auth/logout")
async def logout(response: Response, m2a_session: str | None = Cookie(default=None)):
    user = webauth.get_current_user(m2a_session)
    response.delete_cookie(webauth.SESSION_COOKIE_NAME, path="/")
    if user:
        await db.audit("logout", user)
    return {"ok": True}


@router.get("/auth/me")
async def me(m2a_session: str | None = Cookie(default=None)):
    user = webauth.get_current_user(m2a_session)
    if not user:
        raise HTTPException(401, "Chưa đăng nhập")
    return {"id": user["uid"], "username": user["u"], "role": user["role"]}


@router.get("/admin/users")
async def list_users(_=Depends(webauth.require_role("admin"))):
    pool = _require_db()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, username, role, enabled, created_at, last_login_at FROM users ORDER BY id")
    return {"items": [_public_user(r) for r in rows]}


@router.post("/admin/users")
async def create_user(body: CreateUserBody, request: Request,
                      current=Depends(webauth.require_role("owner"))):
    if body.role not in webauth.ROLE_RANK:
        raise HTTPException(400, "role không hợp lệ")
    pool = _require_db()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "INSERT INTO users (username, password_hash, role) VALUES ($1, $2, $3) "
                "RETURNING id, username, role, enabled, created_at, last_login_at",
                body.username, webauth.hash_password(body.password), body.role)
        except Exception as exc:  # noqa: BLE001 — unique_violation etc.
            raise HTTPException(409, f"Không tạo được user: {exc}") from None
    await db.audit("user_create", current, target=body.username,
                   detail={"role": body.role}, ip=_client_ip(request))
    return _public_user(row)


@router.patch("/admin/users/{user_id}")
async def update_user(user_id: int, body: UpdateUserBody, request: Request,
                      current=Depends(webauth.require_role("owner"))):
    if body.role is not None and body.role not in webauth.ROLE_RANK:
        raise HTTPException(400, "role không hợp lệ")
    pool = _require_db()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE users SET role = COALESCE($2, role), enabled = COALESCE($3, enabled) "
            "WHERE id = $1 RETURNING id, username, role, enabled, created_at, last_login_at",
            user_id, body.role, body.enabled)
    if not row:
        raise HTTPException(404, "Không tìm thấy user")
    await db.audit("role_change", current, target=row["username"],
                   detail={"role": body.role, "enabled": body.enabled}, ip=_client_ip(request))
    return _public_user(row)


@router.delete("/admin/users/{user_id}")
async def delete_user(user_id: int, request: Request, current=Depends(webauth.require_role("owner"))):
    pool = _require_db()
    async with pool.acquire() as conn:
        username = await conn.fetchval("DELETE FROM users WHERE id = $1 RETURNING username", user_id)
        if not username:
            raise HTTPException(404, "Không tìm thấy user")
    await db.audit("user_delete", current, target=username, ip=_client_ip(request))
    return {"deleted": True, "id": user_id}
