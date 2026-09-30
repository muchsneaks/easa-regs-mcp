"""The serverless ASGI app (hosted connector on Vercel) must work without lifespan events."""

from __future__ import annotations

import json
import time

import httpx
import pytest

HEADERS = {"content-type": "application/json", "accept": "application/json, text/event-stream"}


def _rpc(method: str, params: dict | None = None, id_: int = 1) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}})


@pytest.mark.anyio
async def test_asgi_app_without_lifespan(sample_db):
    from easa_regs import asgi
    from easa_regs.server import _con

    _con.cache_clear()
    asgi._last_check = time.time()  # the sample index is fresh; never download in tests
    transport = httpx.ASGITransport(app=asgi.app)  # sends no lifespan events
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/mcp", headers=HEADERS, content=_rpc("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}))
        assert r.status_code == 200 and r.json()["result"]["serverInfo"]["name"] == "easa-regs"

        r = await client.post("/mcp/", headers=HEADERS, content=_rpc("tools/list", id_=2))
        names = {t["name"] for t in r.json()["result"]["tools"]}
        assert {"search_easa_rules", "get_easa_rule", "browse_easa_toc", "list_easa_sources"} <= names

        r = await client.post("/mcp", headers=HEADERS, content=_rpc(
            "tools/call", {"name": "get_easa_rule", "arguments": {"ref": "FCL.740.A"}}, id_=3))
        assert "FCL.740.A" in r.json()["result"]["content"][0]["text"]

        assert (await client.get("/health")).json()["status"] == "ok"
        assert (await client.get("/")).status_code == 200
        assert (await client.get("/nope")).status_code == 404
    _con.cache_clear()


@pytest.fixture
def anyio_backend():
    return "asyncio"
