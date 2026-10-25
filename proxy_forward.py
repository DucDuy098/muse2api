"""Local unauthenticated CONNECT relay that injects Proxy-Authorization for an
upstream authenticated proxy. Chromium strips credentials from --proxy-server,
so headless generation points at this relay instead of the real proxy.
"""
from __future__ import annotations

import asyncio
import base64
import threading
import time

_started_port: int | None = None
_lock = threading.Lock()


async def _relay(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        writer.close()


async def _handle(client_reader, client_writer, upstream_host, upstream_port, auth_header):
    try:
        request_line = await client_reader.readline()
        if not request_line:
            client_writer.close()
            return
        while True:
            line = await client_reader.readline()
            if line in (b"\r\n", b""):
                break
        parts = request_line.decode("latin1").split()
        if len(parts) < 2 or parts[0] != "CONNECT":
            client_writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await client_writer.drain()
            client_writer.close()
            return
        target = parts[1]

        upstream_reader, upstream_writer = await asyncio.open_connection(upstream_host, upstream_port)
        req = f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n"
        if auth_header:
            req += f"Proxy-Authorization: {auth_header}\r\n"
        req += "Proxy-Connection: keep-alive\r\n\r\n"
        upstream_writer.write(req.encode("latin1"))
        await upstream_writer.drain()

        status_line = await upstream_reader.readline()
        while True:
            line = await upstream_reader.readline()
            if line in (b"\r\n", b""):
                break
        if b"200" not in status_line:
            client_writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            await client_writer.drain()
            client_writer.close()
            upstream_writer.close()
            return

        client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await client_writer.drain()

        await asyncio.gather(
            _relay(client_reader, upstream_writer),
            _relay(upstream_reader, client_writer),
        )
    except Exception:
        try:
            client_writer.close()
        except Exception:
            pass


def _start(upstream_host: str, upstream_port: int, username: str | None, password: str | None,
           local_port: int) -> None:
    auth_header = None
    if username:
        token = base64.b64encode(f"{username}:{password or ''}".encode()).decode()
        auth_header = f"Basic {token}"

    def runner():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def main():
            server = await asyncio.start_server(
                lambda r, w: _handle(r, w, upstream_host, upstream_port, auth_header),
                "127.0.0.1", local_port)
            async with server:
                await server.serve_forever()

        loop.run_until_complete(main())

    # ponytail: one asyncio relay thread, fine for the handful of concurrent
    # generation sessions this app drives (MUSE2API_CONCURRENCY). Swap for a
    # pooled/multi-process relay if that concurrency grows much higher.
    threading.Thread(target=runner, daemon=True, name="proxy-forwarder").start()


def ensure_started(upstream_host: str, upstream_port: int, username: str | None,
                    password: str | None, local_port: int) -> int:
    """Idempotent: starts the relay once per process, returns the local port to hand Chromium."""
    global _started_port
    with _lock:
        if _started_port == local_port:
            return local_port
        _start(upstream_host, upstream_port, username, password, local_port)
        time.sleep(0.2)
        _started_port = local_port
        return local_port
