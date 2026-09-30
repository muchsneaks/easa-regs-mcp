"""Serverless-friendly ASGI app for the hosted connector (Vercel, Cloud Run, any ASGI host).

Unlike `easa-regs-mcp --http`, this app does not depend on ASGI lifespan events: every MCP request gets its
own short-lived stateless session manager, so it works on platforms that start a fresh process per request
or never send lifespan events.

The index lives in a writable location (default /tmp/easa_regs.sqlite). It is downloaded from the latest
GitHub release on first use and refreshed once it is older than INDEX_MAX_AGE (default 24 h), so the hosted
connector picks up the weekly EASA update without a redeploy.

Run locally:  uvicorn easa_regs.asgi:app --port 8000   -> http://localhost:8000/mcp
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("EASA_REGS_DB", "/tmp/easa_regs.sqlite")

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402
from starlette.requests import Request  # noqa: E402

from . import db  # noqa: E402
from .fetch import download_index  # noqa: E402
from .server import _con, health, mcp, root  # noqa: E402

INDEX_MAX_AGE = float(os.environ.get("INDEX_MAX_AGE", 24 * 3600))
_ALLOWED = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]
_SECURITY = TransportSecuritySettings(
    enable_dns_rebinding_protection=bool(_ALLOWED), allowed_hosts=_ALLOWED, allowed_origins=[]
)
_last_check = 0.0


def _ensure_index() -> None:
    """Download the index if missing, refresh it when stale (checked at most every 10 minutes)."""
    global _last_check
    now = time.time()
    if now - _last_check < 600:
        return
    _last_check = now
    path = db.db_path()
    if path.exists() and now - path.stat().st_mtime < INDEX_MAX_AGE:
        return
    try:
        download_index(path)
        _con.cache_clear()  # reopen on the new file
    except Exception as exc:  # keep serving the old copy if GitHub is unreachable
        if not path.exists():
            raise
        print(f"Index refresh failed, using existing copy: {exc}", file=sys.stderr)


async def _mcp(scope, receive, send) -> None:  # noqa: ANN001
    manager = StreamableHTTPSessionManager(
        app=mcp._mcp_server, json_response=True, stateless=True, security_settings=_SECURITY
    )
    async with manager.run():
        await manager.handle_request(scope, receive, send)


async def _not_found(scope, receive, send) -> None:  # noqa: ANN001
    await send({"type": "http.response.start", "status": 404,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")]})
    await send({"type": "http.response.body", "body": b"Not found. The MCP endpoint is /mcp"})


async def app(scope, receive, send) -> None:  # noqa: ANN001
    if scope["type"] == "lifespan":  # nothing to set up; acknowledge so hosts that send it are happy
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    if scope["type"] != "http":
        return
    path = scope["path"].rstrip("/") or "/"
    if path == "/mcp":
        _ensure_index()
        scope = dict(scope, path="/mcp")
        await _mcp(scope, receive, send)
    elif path == "/health" and scope["method"] == "GET":
        _ensure_index()
        await (await health(Request(scope, receive)))(scope, receive, send)
    elif path == "/" and scope["method"] == "GET":
        await (await root(Request(scope, receive)))(scope, receive, send)
    else:
        await _not_found(scope, receive, send)


__all__ = ["app"]
