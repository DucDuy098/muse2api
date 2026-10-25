#!/usr/bin/env python3
"""Seed the first 'owner' user. Run once by hand after deploying, with
MUSE2API_DB_URL set and migrations applied (the app runs migrations itself
on startup, so start the service once before running this, or run with
--migrate to apply them here directly).

Usage:
    python scripts/create_owner.py                      # interactive prompts
    python scripts/create_owner.py alice 'S3cret!' --migrate
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

import db
import webauth
from config import CFG


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", nargs="?")
    parser.add_argument("password", nargs="?")
    parser.add_argument("--migrate", action="store_true", help="run migrations before creating the user")
    args = parser.parse_args()

    if not CFG.db_url:
        print("MUSE2API_DB_URL chưa set trong .env — không có gì để làm.", file=sys.stderr)
        return 1

    username = args.username or input("Username: ").strip()
    password = args.password or getpass.getpass("Password: ")
    if not username or not password:
        print("Cần cả username và password.", file=sys.stderr)
        return 1

    pool = await asyncpg.create_pool(CFG.db_url, min_size=1, max_size=2)
    try:
        if args.migrate:
            await db.run_migrations(pool)
        async with pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    "INSERT INTO users (username, password_hash, role) VALUES ($1, $2, 'owner') "
                    "RETURNING id", username, webauth.hash_password(password))
            except asyncpg.UniqueViolationError:
                print(f"User '{username}' đã tồn tại.", file=sys.stderr)
                return 1
        print(f"Đã tạo owner '{username}' (id={row['id']}).")
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
