"""Download the EASA Easy Access Rules XML packages, or a prebuilt index.

Usage:  python -m easa_regs.fetch [BOOK ...]      (default: all books) -> data/raw/<CODE>.zip
        python -m easa_regs.fetch --index          prebuilt SQLite index from the latest GitHub release
Standard library only, so it runs before any dependency is installed.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

from .sources import BOOKS, INDEX_URL

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
UA = "Mozilla/5.0 (easa-regs-mcp; +https://github.com/muchsneaks/easa-regs-mcp) Python-urllib"


def fetch(code: str, raw_dir: Path = RAW_DIR) -> Path:
    book = BOOKS[code]
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / f"{code}.zip"
    tmp = target.with_suffix(".part")
    req = urllib.request.Request(book.xml_url, headers={"User-Agent": UA})
    print(f"[{code}] {book.xml_url}", flush=True)
    with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as fh:
        ctype = resp.headers.get("content-type", "")
        if "zip" not in ctype and "octet-stream" not in ctype:
            raise RuntimeError(f"[{code}] unexpected content-type {ctype!r} - EASA page layout changed?")
        total = 0
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
            total += len(chunk)
    tmp.replace(target)
    print(f"[{code}] saved {total / 1e6:.1f} MB -> {target}", flush=True)
    return target


def download_index(target: Path, url: str = INDEX_URL) -> Path:
    """Fetch the prebuilt index published by the weekly GitHub Action. Logs go to stderr (stdio-safe)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")
    print(f"Downloading prebuilt index {url}", file=sys.stderr, flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as fh:
        while chunk := resp.read(1 << 20):
            fh.write(chunk)
    with open(tmp, "rb") as fh:
        if fh.read(16) != b"SQLite format 3\x00":
            tmp.unlink()
            raise RuntimeError(f"{url} did not return an SQLite file")
    tmp.replace(target)
    print(f"Index saved to {target}", file=sys.stderr, flush=True)
    return target


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if "--index" in args:
        from .db import db_path
        download_index(db_path())
        return
    codes = [c.upper() for c in args] or list(BOOKS)
    for code in codes:
        if code not in BOOKS:
            sys.exit(f"Unknown book {code!r}. Known: {', '.join(BOOKS)}")
        fetch(code)


if __name__ == "__main__":
    main()
