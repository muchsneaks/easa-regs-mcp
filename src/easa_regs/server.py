"""MCP server exposing EASA Easy Access Rules (Aircrew / Part-FCL, Air OPS, SERA).

Run:
    easa-regs-mcp                  # stdio (Claude Desktop, Claude Code, Cursor)
    easa-regs-mcp --http --port 8000   # streamable HTTP at /mcp (hosted)
"""

from __future__ import annotations

import argparse
import sqlite3
from functools import lru_cache
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from . import db
from .fetch import download_index
from .sources import ATTRIBUTION, BOOKS, DISCLAIMER

INSTRUCTIONS = f"""\
Search and quote the EASA Easy Access Rules (EU aviation regulations): Aircrew (Part-FCL, MED, ARA/ORA, DTO), \
Air Operations (ORO, CAT, NCO, NCC, SPO, SPA), SERA, Sailplanes (SFCL/SAO), Balloons (BFCL/BOP), \
Continuing Airworthiness (Part-M/ML/145/CAMO), the Basic Regulation, UAS (drones) and Aerodromes.
Queries work best in English (the rules are in English); common German terms and abbreviations are understood.

How to answer regulatory questions with these tools:
1. Use search_easa_rules to find candidates (natural language or a rule reference such as "FCL.740").
2. Always call get_easa_rule on the rules you rely on and quote the relevant sub-paragraph verbatim.
3. Cite every statement with the rule reference (e.g. "FCL.740(b)(1)") and the book.
4. Distinguish legal force: IR = Implementing Rule (binding), AMC = Acceptable Means of Compliance \
(presumption of compliance, not binding), GM = Guidance Material (explanatory only), CS = Certification Specification.
5. Check the related AMC/GM listed by get_easa_rule - they often contain the practical detail.
6. If the rules do not answer the question, say so. National rules (e.g. LBA/DFS, NfL) and operator \
manuals are NOT covered.
{DISCLAIMER}"""

mcp = FastMCP("easa-regs", instructions=INSTRUCTIONS)
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)

BookCode = Literal["AIRCREW", "AIROPS", "SERA", "SAILPLANES", "BALLOONS", "CONTAIR", "BASIC", "UAS", "AERODROMES"]
BOOK_HELP = ("AIRCREW (Part-FCL/MED/CC/ARA/ORA/DTO), AIROPS (ORO/CAT/NCO/NCC/SPO/SPA/IAM), SERA (rules of the air), "
             "SAILPLANES (Part-SFCL/SAO), BALLOONS (Part-BFCL/BOP), CONTAIR (Part-M/ML/145/CAMO/CAO), "
             "BASIC (Basic Regulation 2018/1139), UAS (drones), AERODROMES")
ContentType = Literal["IR", "AMC", "GM", "CS"]


@lru_cache(maxsize=1)
def _con() -> sqlite3.Connection:
    path = db.db_path()
    if not path.exists():
        try:
            download_index(path)
        except Exception as exc:  # offline, no release yet, ...
            raise RuntimeError(
                f"Index not found at {path} and download failed ({exc}). Build it locally with "
                "`easa-regs-fetch && easa-regs-build`, or run `easa-regs-fetch --index`."
            ) from exc
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


@mcp.tool(title="Search EASA rules", annotations=READ_ONLY, structured_output=False)
def search_easa_rules(
    query: Annotated[str, Field(description="Natural-language question, keywords or a rule reference, "
                                            "e.g. 'SEP class rating revalidation', 'FCL.740', 'VFR minima class G'")],
    book: Annotated[BookCode | None, Field(description="Restrict to one book: " + BOOK_HELP)] = None,
    content_type: Annotated[ContentType | None, Field(description="Restrict to IR, AMC, GM or CS")] = None,
    limit: Annotated[int, Field(ge=1, le=25)] = 8,
) -> dict:
    """Full-text search across EASA Easy Access Rules. Returns ranked rules with reference, type,
    location in the regulation and a matching snippet. Use get_easa_rule to read the full text."""
    hits = db.search(_con(), query, book=book, content_type=content_type, limit=limit)
    return {
        "query": query,
        "results": hits,
        "note": "Snippets are partial. Read the full rule with get_easa_rule before answering." if hits
        else "No match. Try other wording, a rule reference, or drop the book/type filter.",
    }


@mcp.tool(title="Get EASA rule", annotations=READ_ONLY, structured_output=False)
def get_easa_rule(
    ref: Annotated[str, Field(description="Rule reference or title, e.g. 'FCL.740', 'AMC1 FCL.740(b)(1)', "
                                          "'SERA.5005', 'NCO.OP.110', or an ERulesId like 'ERULES-1963177438-9910'")],
    book: Annotated[BookCode | None, Field(description="Disambiguate when the same reference exists in "
                                                       "several books (e.g. 'Article 2')")] = None,
    include_related: Annotated[bool, Field(description="Also list the parent IR and linked AMC/GM")] = True,
    max_chars: Annotated[int, Field(ge=500, le=60000)] = 15000,
) -> dict:
    """Return the full text of one EASA rule (IR, AMC, GM or CS) with metadata, a citation string and
    its related AMC/GM. If the reference is ambiguous, returns the candidates instead."""
    con = _con()
    rows = db.find_rule(con, ref, book=book)
    if not rows:
        hits = db.search(con, ref, book=book, limit=5) or db.nearest_refs(con, ref, book=book)
        return {"found": False, "message": f"No rule matches {ref!r}. Try search_easa_rules.", "did_you_mean": hits}
    exact = [r for r in rows if r["ref_norm"] == db.norm_ref(ref)] or rows
    books = {r["book"] for r in exact}
    if len(books) > 1 and not book:
        return {
            "found": False,
            "message": f"{ref!r} exists in several books - pass book=...",
            "candidates": [db._summary(r) for r in exact],
        }
    row = exact[0]
    text = row["text"] or ""
    truncated = len(text) > max_chars
    out = {
        "found": True,
        "ref": row["ref"],
        "title": row["title"],
        "type": row["content_type"],
        "type_full": row["content_type_full"],
        "book": row["book"],
        "location": row["breadcrumb"],
        "regulatory_source": row["regulatory_source"],
        "applicability_date": row["applicability_date"],
        "entry_into_force_date": row["entry_into_force_date"],
        "regulated_entity": row["regulated_entity"],
        "icao_reference": row["icao_reference"],
        "erules_id": row["erules_id"],
        "text": text[:max_chars] + ("\n[... truncated - raise max_chars]" if truncated else ""),
        "citation": db.citation(con, row),
        "source_url": (db.book_info(con, row["book"]) or {}).get("landing_page", ""),
        "disclaimer": DISCLAIMER,
    }
    if len(rows) > 1:
        out["other_matches"] = [{"ref": r["ref"], "title": r["title"], "type": r["content_type"]}
                                for r in rows[1:6] if r["id"] != row["id"]]
    if include_related:
        out["related"] = db.related(con, row)
    return out


@mcp.tool(title="Browse EASA table of contents", annotations=READ_ONLY, structured_output=False)
def browse_easa_toc(
    book: Annotated[BookCode, Field(description=BOOK_HELP)],
    section_contains: Annotated[str | None, Field(description="Filter sections by text, e.g. 'SUBPART H', "
                                                              "'class and type ratings', 'NCO'")] = None,
    list_rules: Annotated[bool, Field(description="List the rules of the matching sections (max 150)")] = True,
) -> dict:
    """Show the structure of a book (sections with IR/AMC/GM counts). Use it to orient yourself or to list
    every rule in one subpart, e.g. all of Part-FCL Subpart H."""
    con = _con()
    sections = db.toc(con, book, section_contains)
    out: dict = {"book": book, "sections": sections}
    if list_rules and section_contains and sections:
        rules: list[dict] = []
        for sec in sections:
            if len(rules) >= 150:
                out["note"] = "Rule list truncated - narrow section_contains."
                break
            for r in db.section_rules(con, book, sec["breadcrumb"], limit=150 - len(rules)):
                rules.append({**r, "section": sec["breadcrumb"].split(" > ")[-1]})
        out["rules"] = rules
    elif not section_contains:
        out["hint"] = "Pass section_contains (e.g. 'SUBPART H') to list the rules of a section."
    return out


@mcp.tool(title="List indexed EASA books", annotations=READ_ONLY, structured_output=False)
def list_easa_sources() -> dict:
    """List the indexed Easy Access Rules books with their publication date, so answers can state
    which revision they are based on."""
    con = _con()
    rows = [dict(r) for r in con.execute("SELECT code, title, pub_time, landing_page, n_rules, indexed_at FROM books")]
    return {"books": rows, "disclaimer": DISCLAIMER, "attribution": ATTRIBUTION,
            "not_covered": "National rules (LBA, DFS/AIP, NfL), ICAO documents, operator manuals, "
                           "Basic Regulation (EU) 2018/1139 unless reproduced in a book."}


@mcp.resource("easa://disclaimer")
def disclaimer() -> str:
    return f"{DISCLAIMER}\n{ATTRIBUTION}"


def main() -> None:
    ap = argparse.ArgumentParser(description="EASA Easy Access Rules MCP server")
    ap.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    _con()  # fail fast if the index is missing
    if args.http:
        mcp.settings.host, mcp.settings.port = args.host, args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()


__all__ = ["mcp", "main", "BOOKS"]
