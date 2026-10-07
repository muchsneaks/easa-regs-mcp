"""Anonymous, aggregated usage counters for the hosted connector.

Only daily totals are stored, never IP addresses, user agents, search queries or anything else that could
identify a person. Per UTC day we count:
  - MCP requests and JSON-RPC methods (initialize = a client connecting, tools/call = a tool being used)
  - tool names (search_easa_rules, get_easa_rule, ...)
  - the client program from MCP clientInfo (e.g. "claude-ai", "cursor"), reported by the client itself
  - which rules were read with get_easa_rule (rule reference + book, only when the rule exists)

Storage is Upstash Redis over its REST API. Without credentials in the environment every function is a
no-op, so local installs and self-hosted copies never send anything anywhere.
Env (set automatically by the Vercel "Upstash for Redis" integration): KV_REST_API_URL + KV_REST_API_TOKEN,
or UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

KEEP_DAYS = 400
_TRANSPORT = None  # tests inject an httpx.MockTransport here
_SAFE = re.compile(r"[^A-Za-z0-9 ._()\-/]")


def _creds() -> tuple[str, str] | None:
    url = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    return (url.rstrip("/"), token) if url and token else None


def enabled() -> bool:
    return _creds() is not None


def _clean(value: object, limit: int = 60) -> str:
    return _SAFE.sub("", str(value))[:limit] or "unknown"


def events_from_request(body: bytes) -> list[str]:
    """Counter fields for one MCP HTTP request body (a JSON-RPC message or a batch)."""
    try:
        msgs = json.loads(body or b"null")
    except ValueError:
        return ["req", "bad_json"]
    msgs = msgs if isinstance(msgs, list) else [msgs]
    fields = ["req"]
    for m in msgs:
        if not isinstance(m, dict) or "method" not in m:
            continue
        method = _clean(m["method"], 40)
        fields.append(f"m:{method}")
        params = m.get("params") or {}
        if method == "initialize":
            fields.append(f"client:{_clean((params.get('clientInfo') or {}).get('name'))}")
        elif method == "tools/call":
            fields.append(f"tool:{_clean(params.get('name'), 40)}")
    return fields


def refs_from_response(body: bytes) -> list[str]:
    """Rule references (as 'BOOK|REF') that get_easa_rule actually returned in this response."""
    out = []
    try:
        msgs = json.loads(body or b"null")
    except ValueError:
        return out
    for m in msgs if isinstance(msgs, list) else [msgs]:
        for part in ((m or {}).get("result") or {}).get("content") or []:
            if part.get("type") != "text" or '"found": true' not in part.get("text", ""):
                continue
            try:
                data = json.loads(part["text"])
            except ValueError:
                continue
            if data.get("found") and data.get("ref") and data.get("erules_id"):
                out.append(f"{_clean(data.get('book'), 20)}|{_clean(data['ref'], 80)}")
    return out


async def record(fields: list[str], refs: list[str]) -> None:
    creds = _creds()
    if not creds or not (fields or refs):
        return
    url, token = creds
    day = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    cmds = [["HINCRBY", f"day:{day}", f, 1] for f in fields]
    cmds += [["HINCRBY", f"refs:{day}", r, 1] for r in refs]
    cmds += [["EXPIRE", f"day:{day}", KEEP_DAYS * 86400], ["EXPIRE", f"refs:{day}", KEEP_DAYS * 86400]]
    try:
        import httpx

        async with httpx.AsyncClient(timeout=2.0, transport=_TRANSPORT) as client:
            await client.post(f"{url}/pipeline", json=cmds, headers={"Authorization": f"Bearer {token}"})
    except Exception as exc:  # never let statistics break a request
        print(f"stats: {exc}", file=sys.stderr)


async def summary(days: int = 30) -> dict:
    """Daily counters and top rules for the last `days` days."""
    creds = _creds()
    if not creds:
        return {"enabled": False}
    url, token = creds
    today = dt.datetime.now(dt.timezone.utc).date()
    dates = [(today - dt.timedelta(days=i)).isoformat() for i in range(days)]
    cmds = [["HGETALL", f"day:{d}"] for d in dates] + [["HGETALL", f"refs:{d}"] for d in dates]
    import httpx

    async with httpx.AsyncClient(timeout=5.0, transport=_TRANSPORT) as client:
        r = await client.post(f"{url}/pipeline", json=cmds, headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        res = [x.get("result") or [] for x in r.json()]

    def as_dict(flat: list) -> dict[str, int]:
        return {flat[i]: int(flat[i + 1]) for i in range(0, len(flat), 2)}

    per_day, refs, totals = [], {}, {}
    for d, flat in zip(dates, res[:days]):
        counts = as_dict(flat)
        per_day.append({"date": d, **counts})
        for k, v in counts.items():
            totals[k] = totals.get(k, 0) + v
    for flat in res[days:]:
        for k, v in as_dict(flat).items():
            refs[k] = refs.get(k, 0) + v
    top = sorted(refs.items(), key=lambda kv: -kv[1])[:20]
    return {"enabled": True, "days": days, "totals": totals, "per_day": per_day,
            "top_rules": [{"book": k.split("|")[0], "ref": k.split("|", 1)[1], "count": v} for k, v in top]}
