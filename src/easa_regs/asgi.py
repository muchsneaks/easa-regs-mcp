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

from . import db, stats  # noqa: E402
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
    if not stats.enabled():
        async with manager.run():
            await manager.handle_request(scope, receive, send)
        return
    # anonymous usage counters: look at the JSON-RPC method/tool and at which rules were returned
    req, resp = bytearray(), bytearray()

    async def receive_tap():  # noqa: ANN202
        message = await receive()
        if message["type"] == "http.request":
            req.extend(message.get("body", b""))
        return message

    async def send_tap(message) -> None:  # noqa: ANN001
        if message["type"] == "http.response.body" and len(resp) < 2_000_000:
            resp.extend(message.get("body", b""))
        await send(message)

    async with manager.run():
        await manager.handle_request(scope, receive_tap, send_tap)
    if scope.get("method") == "POST":
        await stats.record(stats.events_from_request(bytes(req)), stats.refs_from_response(bytes(resp)))


async def _stats_page(scope, receive, send, as_json: bool) -> None:  # noqa: ANN001
    from starlette.responses import HTMLResponse, JSONResponse

    try:
        data = await stats.summary(30)
    except Exception as exc:  # noqa: BLE001
        data = {"enabled": True, "error": str(exc)}
    resp = JSONResponse(data) if as_json else HTMLResponse(_stats_html(data))
    await resp(scope, receive, send)


def _stats_html(d: dict) -> str:
    import html

    style = ("body{font-family:system-ui,sans-serif;background:#000;color:#F5F5F7;max-width:880px;margin:0 auto;"
             "padding:48px 20px;line-height:1.5}h1{font-size:40px;letter-spacing:-.03em;margin:0 0 4px}"
             "p.s{color:#86868B;margin:0 0 32px}.g{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));"
             "gap:12px;margin-bottom:32px}.c{background:#161618;border:1px solid #2C2C2E;border-radius:18px;padding:18px}"
             ".c b{display:block;font-size:34px;letter-spacing:-.02em;font-variant-numeric:tabular-nums}"
             ".c span{color:#86868B;font-size:14px}h2{font-size:20px;margin:32px 0 12px}table{width:100%;"
             "border-collapse:collapse;font-variant-numeric:tabular-nums}td,th{text-align:left;padding:8px 6px;"
             "border-bottom:1px solid #2C2C2E;font-size:15px}th{color:#86868B;font-weight:500}td.n{text-align:right}"
             "svg text{fill:#86868B;font-size:11px}")
    head = f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>" \
           f"<title>easa-regs usage</title><style>{style}</style><body><h1>easa-regs usage</h1>"
    if not d.get("enabled"):
        return head + "<p class=s>Usage statistics are not configured on this deployment.</p>"
    if d.get("error"):
        return head + f"<p class=s>Could not load statistics: {html.escape(d['error'])}</p>"
    days, t = d["per_day"], d["totals"]

    def last(n: int, key: str) -> int:
        return sum(x.get(key, 0) for x in days[:n])

    cards = [("Connections today", last(1, "m:initialize")), ("Connections, 7 days", last(7, "m:initialize")),
             ("Tool calls, 7 days", last(7, "m:tools/call")), ("Tool calls, 30 days", last(30, "m:tools/call"))]
    out = head + "<p class=s>Anonymous daily totals, last 30 days (UTC). No IP addresses or search terms are stored." \
                 " A connection is one MCP session start (initialize).</p><div class=g>"
    out += "".join(f"<div class=c><b>{v:,}</b><span>{k}</span></div>" for k, v in cards) + "</div>"
    # bar chart: tool calls per day, oldest left
    series = [(x["date"], x.get("m:tools/call", 0), x.get("m:initialize", 0)) for x in reversed(days)]
    peak = max([c for _, c, _ in series] + [1])
    w, h, bw = 840, 160, 840 / len(series)
    bars = "".join(
        f"<rect x='{i*bw+2:.1f}' y='{h-20-(c/peak)*(h-40):.1f}' width='{bw-4:.1f}' height='{(c/peak)*(h-40):.1f}' "
        f"rx='3' fill='#2997FF'><title>{dt}: {c} tool calls, {s} connections</title></rect>"
        for i, (dt, c, s) in enumerate(series))
    labels = f"<text x='0' y='{h-4}'>{series[0][0]}</text><text x='{w}' y='{h-4}' text-anchor='end'>{series[-1][0]}</text>"
    out += f"<h2>Tool calls per day</h2><svg viewBox='0 0 {w} {h}' width='100%' role='img' " \
           f"aria-label='Tool calls per day'>{bars}{labels}<text x='0' y='12'>max {peak}</text></svg>"

    def table(title: str, prefix: str) -> str:
        rows = sorted(((k[len(prefix):], v) for k, v in t.items() if k.startswith(prefix)), key=lambda kv: -kv[1])
        if not rows:
            return ""
        body = "".join(f"<tr><td>{html.escape(k)}</td><td class=n>{v:,}</td></tr>" for k, v in rows)
        return f"<h2>{title}</h2><table><tr><th>Name</th><th style='text-align:right'>30 days</th></tr>{body}</table>"

    out += table("Clients", "client:") + table("Tools", "tool:")
    if d["top_rules"]:
        out += "<h2>Most read rules</h2><table><tr><th>Rule</th><th>Book</th><th style='text-align:right'>30 days</th></tr>"
        out += "".join(f"<tr><td>{html.escape(r['ref'])}</td><td>{html.escape(r['book'])}</td>"
                       f"<td class=n>{r['count']:,}</td></tr>" for r in d["top_rules"]) + "</table>"
    return out


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
    if path == "/mcp" and scope["method"] in ("GET", "DELETE"):
        # No standalone SSE stream: an open GET would keep a serverless instance (and its memory) busy for
        # as long as the client stays connected. The MCP spec allows 405 here; clients then only use POST.
        await send({"type": "http.response.start", "status": 405,
                    "headers": [(b"allow", b"POST"), (b"content-type", b"text/plain; charset=utf-8")]})
        await send({"type": "http.response.body", "body": b"Use POST. This server offers no SSE stream."})
    elif path == "/mcp":
        _ensure_index()
        scope = dict(scope, path="/mcp")
        await _mcp(scope, receive, send)
    elif path == "/health" and scope["method"] == "GET":
        _ensure_index()
        await (await health(Request(scope, receive)))(scope, receive, send)
    elif path in ("/stats", "/stats.json") and scope["method"] == "GET":
        await _stats_page(scope, receive, send, as_json=path.endswith(".json"))
    elif path == "/" and scope["method"] == "GET":
        await (await root(Request(scope, receive)))(scope, receive, send)
    else:
        await _not_found(scope, receive, send)


__all__ = ["app"]
