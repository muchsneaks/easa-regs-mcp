"""Build (or rebuild) the SQLite index from downloaded EASA XML packages.

Usage:  python -m easa_regs.build [--db PATH] [--raw DIR] [BOOK ...]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from . import db
from .fetch import RAW_DIR
from .parse import parse_book
from .sources import BOOKS


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("books", nargs="*", help=f"book codes (default: all found). Known: {', '.join(BOOKS)}")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: data/easa_regs.sqlite)")
    ap.add_argument("--raw", type=Path, default=RAW_DIR, help="directory with <CODE>.zip files")
    args = ap.parse_args(argv)

    codes = [c.upper() for c in args.books] or [c for c in BOOKS if (args.raw / f"{c}.zip").exists()]
    if not codes:
        raise SystemExit(f"No packages in {args.raw}. Run `python -m easa_regs.fetch` first.")
    target = args.db or db.db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    con = db.connect(target)
    for code in codes:
        src = args.raw / f"{code}.zip"
        t0 = time.time()
        parsed = parse_book(src, code)
        n = db.store_book(con, parsed)
        types: dict[str, int] = {}
        for r in parsed.rules:
            types[r.content_type] = types.get(r.content_type, 0) + 1
        print(f"[{code}] {n} rules {types} (published {parsed.pub_time[:10]}) in {time.time() - t0:.1f}s")
    manifest = {
        r["code"]: {"pub_time": r["pub_time"], "n_rules": r["n_rules"], "title": r["title"]}
        for r in con.execute("SELECT code, pub_time, n_rules, title FROM books ORDER BY code")
    }
    (target.parent / "manifest.json").write_text(json.dumps(manifest, indent=2))
    con.execute("INSERT INTO rules_fts(rules_fts) VALUES('optimize')")
    con.commit()
    con.execute("VACUUM")
    print(f"Index written to {target} ({target.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
