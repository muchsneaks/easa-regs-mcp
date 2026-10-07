"""Anonymous usage counters: what gets counted, and that nothing is sent without credentials."""

from __future__ import annotations

import json
import time

import httpx
import pytest

from easa_regs import stats

HEADERS = {"content-type": "application/json", "accept": "application/json, text/event-stream"}


class FakeRedis:
    """Minimal Upstash REST /pipeline emulation (HINCRBY, EXPIRE, HGETALL)."""

    def __init__(self) -> None:
        self.h: dict[str, dict[str, int]] = {}
        self.calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer tok"
        self.calls += 1
        out = []
        for cmd in json.loads(request.content):
            op, key = cmd[0], cmd[1]
            if op == "HINCRBY":
                d = self.h.setdefault(key, {})
                d[cmd[2]] = d.get(cmd[2], 0) + int(cmd[3])
                out.append({"result": d[cmd[2]]})
            elif op == "HGETALL":
                flat = [x for kv in self.h.get(key, {}).items() for x in (kv[0], str(kv[1]))]
                out.append({"result": flat})
            else:
                out.append({"result": 1})
        return httpx.Response(200, json=out)


def test_event_extraction():
    init = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"clientInfo": {"name": "claude-ai", "version": "1"}}}).encode()
    assert stats.events_from_request(init) == ["req", "m:initialize", "client:claude-ai"]
    call = json.dumps([{"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                        "params": {"name": "search_easa_rules", "arguments": {"query": "my private question"}}}]).encode()
    ev = stats.events_from_request(call)
    assert ev == ["req", "m:tools/call", "tool:search_easa_rules"]
    assert not any("private" in e for e in ev)  # arguments (search terms) are never counted
    assert stats.events_from_request(b"{not json") == ["req", "bad_json"]


def test_no_credentials_means_no_network(monkeypatch):
    for k in ("KV_REST_API_URL", "KV_REST_API_TOKEN", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    assert not stats.enabled()


@pytest.mark.anyio
async def test_counts_through_asgi_app(sample_db, monkeypatch):
    from easa_regs import asgi
    from easa_regs.server import _con

    fake = FakeRedis()
    monkeypatch.setenv("KV_REST_API_URL", "https://redis.test")
    monkeypatch.setenv("KV_REST_API_TOKEN", "tok")
    monkeypatch.setattr(stats, "_TRANSPORT", httpx.MockTransport(fake.handler))
    _con.cache_clear()
    asgi._last_check = time.time()
    rpc = lambda m, p, i: json.dumps({"jsonrpc": "2.0", "id": i, "method": m, "params": p})  # noqa: E731
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=asgi.app), base_url="http://t") as c:
        await c.post("/mcp", headers=HEADERS, content=rpc("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "cursor", "version": "1"}}, 1))
        await c.post("/mcp", headers=HEADERS, content=rpc(
            "tools/call", {"name": "get_easa_rule", "arguments": {"ref": "SERA.5005"}}, 2))
        await c.post("/mcp", headers=HEADERS, content=rpc(
            "tools/call", {"name": "get_easa_rule", "arguments": {"ref": "NOPE.999"}}, 3))
        summary = (await c.get("/stats.json")).json()
        page = await c.get("/stats")
    _con.cache_clear()

    t = summary["totals"]
    assert t["req"] == 3 and t["m:initialize"] == 1 and t["client:cursor"] == 1
    assert t["m:tools/call"] == 2 and t["tool:get_easa_rule"] == 2
    assert summary["top_rules"] == [{"book": "SERA", "ref": "SERA.5005", "count": 1}]  # only rules that exist
    assert page.status_code == 200 and "SERA.5005" in page.text and "cursor" in page.text
    dump = json.dumps(fake.h)
    assert "NOPE" not in dump  # unknown refs are not stored


@pytest.fixture
def anyio_backend():
    return "asyncio"
