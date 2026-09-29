"""SQLite + FTS5 index over parsed EASA rules, plus the query layer used by the MCP tools."""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .parse import ParsedBook, norm_ref
from .sources import BOOKS

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _default_db() -> Path:
    """Repo checkout -> <repo>/data; installed package (pip/uvx) -> per-user data dir."""
    if (_REPO_ROOT / "pyproject.toml").exists():
        return _REPO_ROOT / "data" / "easa_regs.sqlite"
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "easa-regs-mcp" / "easa_regs.sqlite"


DEFAULT_DB = _default_db()

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    code TEXT PRIMARY KEY,
    title TEXT,
    source_title TEXT,
    pub_time TEXT,
    landing_page TEXT,
    indexed_at TEXT,
    n_rules INTEGER
);
CREATE TABLE IF NOT EXISTS rules (
    id INTEGER PRIMARY KEY,
    erules_id TEXT,
    book TEXT,
    seq INTEGER,
    title TEXT,
    ref TEXT,
    ref_norm TEXT,
    heading TEXT,
    content_type TEXT,
    content_type_full TEXT,
    parent_ir TEXT,
    regulatory_source TEXT,
    applicability_date TEXT,
    entry_into_force_date TEXT,
    domain TEXT,
    keywords TEXT,
    regulated_entity TEXT,
    regulatory_subject TEXT,
    icao_reference TEXT,
    breadcrumb TEXT,
    text TEXT
);
CREATE INDEX IF NOT EXISTS rules_ref ON rules(ref_norm);
CREATE INDEX IF NOT EXISTS rules_book ON rules(book, seq);
CREATE INDEX IF NOT EXISTS rules_parent ON rules(book, parent_ir);
CREATE INDEX IF NOT EXISTS rules_erid ON rules(erules_id);
CREATE VIRTUAL TABLE IF NOT EXISTS rules_fts USING fts5(
    ref, title, breadcrumb, keywords, text,
    content='rules', content_rowid='id',
    tokenize="porter unicode61 remove_diacritics 2"
);
"""

TYPE_ORDER = "CASE content_type WHEN 'IR' THEN 0 WHEN 'AMC' THEN 1 WHEN 'GM' THEN 2 WHEN 'CS' THEN 3 ELSE 4 END"
REF_TOKEN = re.compile(r"\b(?:(?:AMC|GM|CS)\d*\s+)?[A-Z]{2,}[A-Z0-9]*(?:\.[A-Z0-9]+)+(?:\([a-z0-9]+\))*", re.I)


def db_path() -> Path:
    return Path(os.environ.get("EASA_REGS_DB", DEFAULT_DB))


def connect(path: Path | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(str(path or db_path()))
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def store_book(con: sqlite3.Connection, parsed: ParsedBook) -> int:
    book = BOOKS.get(parsed.code)
    with con:
        ids = [r[0] for r in con.execute("SELECT id FROM rules WHERE book=?", (parsed.code,))]
        if ids:
            con.executemany(
                "INSERT INTO rules_fts(rules_fts, rowid, ref, title, breadcrumb, keywords, text) "
                "SELECT 'delete', id, ref, title, breadcrumb, keywords, text FROM rules WHERE id=?",
                [(i,) for i in ids],
            )
            con.execute("DELETE FROM rules WHERE book=?", (parsed.code,))
        for r in parsed.rules:
            d = asdict(r)
            d["ref_norm"] = norm_ref(r.ref)
            cols = ",".join(d)
            cur = con.execute(f"INSERT INTO rules({cols}) VALUES ({','.join('?' * len(d))})", tuple(d.values()))
            con.execute(
                "INSERT INTO rules_fts(rowid, ref, title, breadcrumb, keywords, text) VALUES (?,?,?,?,?,?)",
                (cur.lastrowid, r.ref, r.title, r.breadcrumb, r.keywords, r.text),
            )
        con.execute(
            "INSERT OR REPLACE INTO books VALUES (?,?,?,?,?,?,?)",
            (
                parsed.code,
                book.title if book else parsed.source_title,
                parsed.source_title,
                parsed.pub_time,
                book.landing_page if book else "",
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                len(parsed.rules),
            ),
        )
    return len(parsed.rules)


# --------------------------------------------------------------------------- queries

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from", "how", "i", "in",
    "is", "it", "my", "of", "on", "or", "the", "to", "what", "when", "which", "who", "with", "under",
    "rule", "rules", "requirement", "requirements", "easa", "regulation",
}


# Abbreviations and common German terms -> English wording used in the rules.
# Each query term matches if the term itself OR its expansion is present.
EXPANSIONS = {
    # abbreviations
    "vfr": "visual flight rules", "ifr": "instrument flight rules", "svfr": "special VFR",
    "vmc": "visual meteorological conditions", "imc": "instrument meteorological conditions",
    "pic": "pilot-in-command", "fi": "flight instructor", "cri": "class rating instructor",
    "fe": "flight examiner", "ato": "approved training organisation", "dto": "declared training organisation",
    "tmg": "touring motor glider", "sep": "single-engine piston", "mep": "multi-engine piston",
    "set": "single-engine turbo-prop", "ncc": "non-commercial complex", "nco": "non-commercial",
    "cat": "commercial air transport", "elt": "emergency locator transmitter", "ftl": "flight time limitations",
    "fdp": "flight duty period", "pbn": "performance-based navigation", "ebt": "evidence-based training",
    "uprt": "upset prevention and recovery training", "mcc": "multi-crew cooperation", "tk": "theoretical knowledge",
    "lpc": "licence proficiency check", "opc": "operator proficiency check", "crm": "crew resource management",
    "fstd": "flight simulation training device", "ffs": "full flight simulator", "om": "operations manual",
    "ctr": "control zone", "atz": "aerodrome traffic zone", "tmz": "transponder mandatory zone",
    "rmz": "radio mandatory zone", "ame": "aero-medical examiner", "aemc": "aero-medical centre",
    # German
    "verlängerung": "revalidation", "verlaengerung": "revalidation", "erneuerung": "renewal",
    "klassenberechtigung": "class rating", "musterberechtigung": "type rating", "nachtflug": "night",
    "nachtflugberechtigung": "night rating", "fluglehrer": "flight instructor", "lehrberechtigung": "instructor certificate",
    "prüfer": "examiner", "pruefer": "examiner", "sprachprüfung": "language proficiency",
    "sprachkenntnisse": "language proficiency", "tauglichkeitszeugnis": "medical certificate",
    "tauglichkeit": "medical", "flugbuch": "logbook", "passagiere": "passengers", "fluggäste": "passengers",
    "kraftstoff": "fuel", "treibstoff": "fuel", "sprit": "fuel", "sauerstoff": "oxygen", "sichtflug": "VFR",
    "instrumentenflug": "IFR", "luftraum": "airspace", "mindesthöhe": "minimum height",
    "mindesthöhen": "minimum heights", "flugplan": "flight plan", "funkausfall": "communication failure",
    "ausweichflugplatz": "alternate aerodrome", "flugschüler": "student pilot", "alleinflug": "solo",
    "kunstflug": "aerobatic", "schleppberechtigung": "towing rating", "segelflug": "sailplane",
    "segelflugzeug": "sailplane", "motorsegler": "touring motor glider", "wetter": "meteorological",
    "gültigkeit": "validity", "voraussetzungen": "prerequisites", "ausbildung": "training",
    "flugstunden": "flight time", "flugzeit": "flight time", "landungen": "landings", "starts": "take-offs",
    "befähigungsüberprüfung": "proficiency check", "prüfungsflug": "skill test", "theorieprüfung":
    "theoretical knowledge examination", "flugzeug": "aeroplane", "hubschrauber": "helicopter",
    "notsender": "emergency locator transmitter", "schwimmwesten": "life-jackets",
    "kommandant": "pilot-in-command", "flugschule": "training organisation", "lizenz": "licence",
    "berechtigung": "rating", "rechte": "privileges", "anforderungen": "requirements",
    "übungsflug": "training flight", "auffrischungsschulung": "refresher training",
    "erfahrung": "experience", "vorflug": "pre-flight", "flugvorbereitung": "flight preparation",
    "nacht": "night", "tag": "day", "gäste": "passengers", "dauer": "duration",
}
_DE_PREFIXES = sorted((k for k in EXPANSIONS if len(k) >= 7 and not k.isascii() or len(k) >= 9), key=len, reverse=True)


def _terms(q: str) -> list[str]:
    out = []
    for t in re.findall(r"[\w.\-()]+", q, flags=re.UNICODE):
        t = t.strip(".-()")
        if not t or t.lower() in STOPWORDS or (len(t) < 2 and not t.isdigit()):
            continue
        out.append(t)
    return out


def _expansion(term: str) -> str | None:
    low = term.lower()
    if low in EXPANSIONS:
        return EXPANSIONS[low]
    base = re.sub(r"\(.*$", "", low)                 # 'fi(a)' -> 'fi'
    if base in EXPANSIONS:
        return EXPANSIONS[base]
    for k in _DE_PREFIXES:                            # German plurals/compounds: 'klassenberechtigungen'
        if low.startswith(k):
            return EXPANSIONS[k]
    return None


def _groups(q: str) -> list[list[list[str]]]:
    """Per query term: alternatives, each a list of word stems that must all be present."""
    groups = []
    for t in _terms(q):
        alts = [[_stem(w) for w in re.findall(r"\w+", t) if len(w) >= 2 or w.isdigit()]]
        exp = _expansion(t)
        if exp:
            alts.append([_stem(w) for w in re.findall(r"\w+", exp) if len(w) >= 2])
        alts = [a for a in alts if a]
        if alts:
            groups.append(alts)
    return groups


def _fts_query(q: str, mode: str = "AND") -> str:
    parts = []
    for t in _terms(q):
        alts = ['"' + t.replace('"', "") + '"' + ("*" if len(t) >= 4 and not any(c in t for c in ".()") else "")]
        exp = _expansion(t)
        if exp:
            alts.append('"' + exp.replace('"', "") + '"')
        parts.append(alts[0] if len(alts) == 1 else "(" + " OR ".join(alts) + ")")
    return f" {mode} ".join(parts)


def _stem(w: str) -> str:
    return w.lower()[:5]


def _coverage(groups: list[list[list[str]]], words: set[str]) -> float:
    if not groups:
        return 0.0
    hit = sum(1 for alts in groups if any(all(s in words for s in alt) for alt in alts))
    return hit / len(groups)


AUTHORITY_HINTS = re.compile(r"\b(authority|authorities|oversight|ARA|ARO|behörde|LBA)\b", re.I)


SPECIFIC_HINTS = re.compile(
    r"\b(CAT|commercial|air transport|AOC|SPO|specialised|SPA|HEMS|HOFO|PBN|ETOPS|UAM|IAM|VTOL|VCA|NCC|complex|"
    r"airline|operator|gewerblich)\b", re.I)


def _rerank_score(row: sqlite3.Row, groups: list, best: float, authority_query: bool = False,
                  specific_query: bool = False) -> float:
    """bm25 is dominated by long texts; reward rules whose title/location carry the query terms."""
    rel = row["rank"] / best if best else 0.0          # 1.0 for the best bm25 hit
    if not groups:
        return rel
    title = {_stem(w) for w in re.findall(r"\w+", row["title"] or "")}
    crumbs = {_stem(w) for w in re.findall(r"\w+", row["breadcrumb"] or "")}
    body = title | crumbs | {_stem(w) for w in re.findall(r"\w+", row["text"] or "")}
    score = 2.0 * rel + 3.0 * _coverage(groups, title) + 0.8 * _coverage(groups, crumbs) \
        + 2.0 * _coverage(groups, body)             # ~AND semantics without losing OR recall
    score += {"IR": 0.3, "AMC": 0.15, "GM": 0.05}.get(row["content_type"], 0.0)
    # most users are pilots/organisations: authority-side rules (ARA/ARO) only when asked for
    if not authority_query and re.match(r"^(?:(?:AMC|GM)\d*\s+)?AR[AO]\.", row["ref"] or ""):
        score -= 1.0
    # operation-specific parts (CAT, SPO, SPA, IAM, NCC) only win when the question is about them
    if not specific_query and re.match(r"^(?:(?:AMC|GM)\d*\s+)?(?:CAT|SPO|SPA|UAM|NCC)\.", row["ref"] or ""):
        score -= 0.5
    return score


def _filters(book: str | None, content_type: str | None, alias: str = "r") -> tuple[str, list]:
    sql, args = "", []
    if book:
        sql += f" AND {alias}.book = ?"
        args.append(book.upper())
    if content_type:
        types = [t.strip().upper() for t in content_type.split(",") if t.strip()]
        sql += f" AND {alias}.content_type IN ({','.join('?' * len(types))})"
        args += types
    return sql, args


def search(con, query: str, book=None, content_type=None, limit: int = 8) -> list[dict]:
    limit = max(1, min(int(limit), 25))
    results: list[dict] = []
    seen: set[int] = set()
    fsql, fargs = _filters(book, content_type)

    # 1) explicit rule references in the query ("FCL.740", "AMC1 NCO.OP.110") go first
    for m in REF_TOKEN.finditer(query):
        key = norm_ref(m.group(0))
        rows = con.execute(
            f"SELECT r.*, '' AS snip FROM rules r WHERE (r.ref_norm = ? OR r.ref_norm LIKE ? OR r.ref_norm LIKE ?){fsql} "
            f"ORDER BY (r.ref_norm = ?) DESC, {TYPE_ORDER}, r.seq LIMIT ?",
            [key, key + "(%", "%" + key + "%", key, *fargs, limit],
        ).fetchall()
        for row in rows:
            if row["id"] not in seen:
                seen.add(row["id"])
                results.append(_summary(row))

    # 2) full-text: OR-query for recall, then rerank the pool (bm25 + title/section/term coverage)
    groups = _groups(query)
    authority_query = bool(AUTHORITY_HINTS.search(query))
    specific_query = bool(SPECIFIC_HINTS.search(query))
    fq = _fts_query(query, "OR")
    if fq and len(results) < limit:
        rows = con.execute(
            "SELECT r.*, snippet(rules_fts, 4, '**', '**', ' ... ', 24) AS snip, "
            "bm25(rules_fts, 8.0, 5.0, 1.5, 3.0, 1.0) AS rank "
            "FROM rules_fts JOIN rules r ON r.id = rules_fts.rowid "
            f"WHERE rules_fts MATCH ?{fsql} ORDER BY rank LIMIT 150",
            [fq, *fargs],
        ).fetchall()
        best = min((r["rank"] for r in rows), default=0.0)
        for row in sorted(rows, key=lambda r: _rerank_score(r, groups, best, authority_query, specific_query),
                          reverse=True):
            if len(results) >= limit:
                break
            # an AMC/GM hit means its parent IR is relevant too: show the binding rule first
            if row["content_type"] in ("AMC", "GM") and row["parent_ir"]:
                parent = con.execute(
                    f"SELECT r.*, '' AS snip FROM rules r WHERE r.book=? AND r.title=?{fsql} LIMIT 1",
                    [row["book"], row["parent_ir"], *fargs],
                ).fetchone()
                if parent is not None and parent["id"] not in seen:
                    seen.add(parent["id"])
                    results.append({**_summary(parent), "why": f"parent rule of {row['ref']}"})
            if row["id"] not in seen and len(results) < limit:
                seen.add(row["id"])
                results.append(_summary(row))
    return results[:limit]


def _summary(row: sqlite3.Row) -> dict:
    snip = row["snip"] if "snip" in row.keys() else ""
    if not snip:
        snip = (row["text"] or "")[:280].replace("\n", " ") + ("..." if len(row["text"] or "") > 280 else "")
    return {
        "ref": row["ref"],
        "title": row["title"],
        "type": row["content_type"],
        "book": row["book"],
        "location": row["breadcrumb"],
        "applicability_date": row["applicability_date"],
        "erules_id": row["erules_id"],
        "snippet": snip.replace("\n", " "),
    }


def find_rule(con, ref_or_id: str, book: str | None = None) -> list[sqlite3.Row]:
    """Resolve a user-supplied reference to candidate rows (best first)."""
    fsql, fargs = _filters(book, None)
    s = ref_or_id.strip()
    if s.upper().startswith("ERULES-"):
        return con.execute(f"SELECT * FROM rules r WHERE r.erules_id = ?{fsql}", [s.upper(), *fargs]).fetchall()
    key = norm_ref(s)
    for sql, args in (
        ("r.ref_norm = ?", [key]),
        ("lower(replace(r.title,' ','')) = ?", [key]),
        ("r.ref_norm LIKE ?", [key + "(%"]),
        ("lower(replace(r.title,' ','')) LIKE ?", [key + "%"]),
    ):
        rows = con.execute(
            f"SELECT * FROM rules r WHERE {sql}{fsql} ORDER BY {TYPE_ORDER}, r.seq LIMIT 10", [*args, *fargs]
        ).fetchall()
        if rows:
            return rows
    return []


def nearest_refs(con, ref: str, book: str | None = None, limit: int = 5) -> list[dict]:
    """Rules whose reference shares the longest prefix with an unknown ref ('FCL.9999' -> 'FCL.9...')."""
    fsql, fargs = _filters(book, None)
    key = norm_ref(ref)
    while len(key) >= 4:
        key = key[:-1]
        rows = con.execute(
            f"SELECT r.*, '' AS snip FROM rules r WHERE r.ref_norm LIKE ?{fsql} ORDER BY {TYPE_ORDER}, r.seq LIMIT ?",
            [key + "%", *fargs, limit],
        ).fetchall()
        if rows:
            return [_summary(r) for r in rows]
    return []


def related(con, row: sqlite3.Row) -> dict:
    children = con.execute(
        f"SELECT ref, title, content_type, erules_id FROM rules WHERE book=? AND parent_ir=? ORDER BY {TYPE_ORDER}, seq",
        (row["book"], row["title"]),
    ).fetchall()
    parent = None
    if row["parent_ir"]:
        p = con.execute(
            "SELECT ref, title, content_type, erules_id FROM rules WHERE book=? AND title=? LIMIT 1",
            (row["book"], row["parent_ir"]),
        ).fetchone()
        parent = dict(p) if p else {"title": row["parent_ir"]}
    return {"parent": parent, "amc_gm": [dict(c) for c in children]}


def book_info(con, code: str) -> dict | None:
    r = con.execute("SELECT * FROM books WHERE code=?", (code,)).fetchone()
    return dict(r) if r else None


def citation(con, row: sqlite3.Row) -> str:
    b = book_info(con, row["book"]) or {}
    pub = (b.get("pub_time") or "")[:10]
    parts = [row["title"], f"{b.get('title', row['book'])} (published {pub})" if pub else b.get("title", row["book"])]
    if row["regulatory_source"]:
        parts.append(f"as amended by {row['regulatory_source']}")
    parts.append(f"ERulesId {row['erules_id']}")
    return " - ".join(parts)


def toc(con, book: str, contains: str | None = None, max_items: int = 200) -> list[dict]:
    rows = con.execute(
        "SELECT breadcrumb, COUNT(*) n, "
        "SUM(content_type='IR') ir, SUM(content_type='AMC') amc, SUM(content_type='GM') gm, MIN(seq) first "
        "FROM rules WHERE book=? GROUP BY breadcrumb ORDER BY first",
        (book.upper(),),
    ).fetchall()
    out = [dict(r) for r in rows if not contains or contains.lower() in (r["breadcrumb"] or "").lower()]
    for o in out:
        o.pop("first", None)
    return out[:max_items]


def section_rules(con, book: str, breadcrumb: str, content_type: str | None = None, limit: int = 100) -> list[dict]:
    fsql, fargs = _filters(None, content_type)
    rows = con.execute(
        f"SELECT ref, title, content_type, erules_id FROM rules r WHERE r.book=? AND r.breadcrumb=?{fsql} "
        "ORDER BY r.seq LIMIT ?",
        [book.upper(), breadcrumb, *fargs, limit],
    ).fetchall()
    return [dict(r) for r in rows]
