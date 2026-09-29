"""Build (or rebuild) the SQLite index from downloaded EASA XML packages.

Usage:  python -m easa_regs.build [--db PATH] [--raw DIR] [BOOK ...]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
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
    ap.add_argument("--keep-going", action="store_true", help="index the other books if one fails to parse")
    args = ap.parse_args(argv)

    codes = [c.upper() for c in args.books] or [c for c in BOOKS if (args.raw / f"{c}.zip").exists()]
    if not codes:
        raise SystemExit(f"No packages in {args.raw}. Run `python -m easa_regs.fetch` first.")
    target = args.db or db.db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    con = db.connect(target)
    failures: dict[str, str] = {}
    for code in codes:
        src = args.raw / f"{code}.zip"
        t0 = time.time()
        try:
            parsed = parse_book(src, code)
            if not parsed.rules:
                raise ValueError("no rules parsed")
            n = db.store_book(con, parsed)
        except Exception as exc:
            failures[code] = f"{type(exc).__name__}: {exc}"
            print(f"[{code}] FAILED - {failures[code]}", file=sys.stderr)
            traceback.print_exc()
            continue
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
    errors_file = target.parent / "build_errors.txt"
    if failures:
        errors_file.write_text("\n".join(f"{c}: {e}" for c, e in failures.items()) + "\n")
        if not args.keep_going:
            raise SystemExit(f"{len(failures)} book(s) failed: {', '.join(failures)}")
    elif errors_file.exists():
        errors_file.unlink()


if __name__ == "__main__":
    main()
