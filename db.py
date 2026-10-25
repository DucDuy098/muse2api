"""Postgres pool + plain-SQL migrations for the team web UI (users/audit_log).
The core generation engine never imports this module — if MUSE2API_DB_URL is
unset or Postgres is unreachable, image/video generation keeps working.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import asyncpg

from config import CFG

log = logging.getLogger("muse2api.db")

MIGRATIONS_DIR = os.path.join(CFG.base_dir, "migrations")

POOL: asyncpg.Pool | None = None
_MAIN_LOOP: asyncio.AbstractEventLoop | None = None


async def run_migrations(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        applied = {r["filename"] for r in await conn.fetch("SELECT filename FROM schema_migrations")}
        if not os.path.isdir(MIGRATIONS_DIR):
            return
        for filename in sorted(os.listdir(MIGRATIONS_DIR)):
            if not filename.endswith(".sql") or filename in applied:
                continue
            path = os.path.join(MIGRATIONS_DIR, filename)
            with open(path, encoding="utf-8") as f:
                sql = f.read()
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES ($1)", filename
                )
            log.info("đã áp dụng migration: %s", filename)


async def init() -> None:
    """Best-effort: a DB outage must never take down image/video generation."""
    global POOL, _MAIN_LOOP
    _MAIN_LOOP = asyncio.get_running_loop()
    if not CFG.db_url:
        log.info("MUSE2API_DB_URL trống — bỏ qua lớp web auth/audit log")
        return
    try:
        POOL = await asyncpg.create_pool(CFG.db_url, min_size=1, max_size=5)
        await run_migrations(POOL)
    except Exception as exc:  # noqa: BLE001
        log.warning("Không kết nối được Postgres (%s) — web auth/audit log tạm tắt, engine vẫn chạy bình thường", exc)
        POOL = None


async def close() -> None:
    global POOL
    if POOL is not None:
        await POOL.close()
        POOL = None


async def audit(action: str, user: dict | None, target: str | None = None,
                 detail: dict | None = None, ip: str | None = None) -> None:
    if POOL is None:
        return
    try:
        async with POOL.acquire() as conn:
            await conn.execute(
                "INSERT INTO audit_log (user_id, username, action, target, detail, ip) "
                "VALUES ($1, $2, $3, $4, $5::jsonb, $6)",
                (user or {}).get("uid"), (user or {}).get("u"), action, target,
                json.dumps(detail) if detail is not None else None, ip,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("audit log insert thất bại (%s): %s", action, exc)


def audit_threadsafe(action: str, user: dict | None, target: str | None = None,
                      detail: dict | None = None, ip: str | None = None) -> None:
    """For callers running in a worker thread (e.g. the generation workers in
    app.py), not the asyncio loop — schedules audit() onto the main loop and
    does not wait for it. Mirrors task_events.TaskBus.publish_threadsafe."""
    if POOL is None or _MAIN_LOOP is None:
        return
    asyncio.run_coroutine_threadsafe(audit(action, user, target, detail, ip), _MAIN_LOOP)
