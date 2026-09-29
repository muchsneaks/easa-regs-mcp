"""Parse an EASA Easy Access Rules XML package into rule records.

Package layout (as published by EASA, Flat OPC / Word 2003 XML):

    pkg:package
      pkg:part name="/customXml/itemN.xml"   -> er:document (TOC + metadata per topic)
      pkg:part name="/word/document.xml"     -> w:document (the actual text)

``er:document`` holds nested ``er:toc`` / ``er:heading`` / ``er:topic`` elements.
Each ``er:topic`` carries a stable ``ERulesId`` plus metadata, and an ``sdt-id``
that points at the ``w:sdt`` (tag="topic") in word/document.xml with the text.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Iterator

from lxml import etree

NS = {
    "pkg": "http://schemas.microsoft.com/office/2006/xmlPackage",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "er": "http://www.easa.europa.eu/erules-export",
}
PKG_PART = f"{{{NS['pkg']}}}part"
PKG_NAME = f"{{{NS['pkg']}}}name"
W = f"{{{NS['w']}}}"
ER = f"{{{NS['er']}}}"

SKIP_TYPES = {
    "disclaimer", "list of revisions", "note from the editor", "table of contents",
    "incorporated amendments", "easy access rules", "n/a",
}
# some books (e.g. Basic Regulation) leave TypeOfContent empty - skip their front matter by title
FRONTMATTER_TITLES = SKIP_TYPES | {"easa erules", "cover page", "foreword"}


@dataclass
class Rule:
    erules_id: str
    book: str
    seq: int
    title: str
    ref: str
    heading: str
    content_type: str          # IR | AMC | GM | CS | OTHER
    content_type_full: str
    parent_ir: str
    regulatory_source: str
    applicability_date: str
    entry_into_force_date: str
    domain: str
    keywords: str
    regulated_entity: str
    regulatory_subject: str
    icao_reference: str
    breadcrumb: str
    text: str


@dataclass
class ParsedBook:
    code: str
    source_title: str
    pub_time: str
    rules: list[Rule] = field(default_factory=list)


# --------------------------------------------------------------------------- refs

_PREFIX = re.compile(r"^(?:AMC|GM|CS|AMC-GM)\d*$")
# 'FCL.740(b)', 'ORO.GEN.310(b);(d)', 'NCC.IDE.A.120&NCC.IDE.A.125', 'Part-FCL'
_DOTTED = re.compile(r"^(?:[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*\.[A-Za-z0-9]\S*|Part-[A-Z]{2,}\S*)$")
_NUMBERISH = re.compile(r"^(?:\d+[a-z]?|[IVXLC]+|[A-Z])(?:\([^)\s]*\))*[;,]?$")
_KEYWORDS = {"Article", "Appendix", "Annex", "ANNEX", "Section", "SECTION", "SUBJECT"}


def split_ref(title: str) -> tuple[str, str]:
    """Split 'AMC1 FCL.740(b) Validity of ratings' -> ('AMC1 FCL.740(b)', 'Validity of ratings').

    Handles 'SERA.5005 ...', 'GM1 Article 2(25) ...', 'Appendix 1 to Part-FCL ...',
    'AMC1 ORO.FC.100(c);(d) ...'. Falls back to (title, '') when no ref is found.
    """
    tokens = title.split()
    out: list[str] = []
    i = 0
    if i < len(tokens) and _PREFIX.match(tokens[i]):
        out.append(tokens[i]); i += 1
        if i < len(tokens) and tokens[i] == "to":      # 'AMC to ...'
            out.append(tokens[i]); i += 1
        if i < len(tokens) and tokens[i] == "CS":      # 'GM1 CS FTL.1.205'
            out.append(tokens[i]); i += 1
    if i < len(tokens) and tokens[i] in _KEYWORDS:
        out.append(tokens[i]); i += 1
        if i < len(tokens) and _NUMBERISH.match(tokens[i]):
            out.append(tokens[i]); i += 1
        # 'Appendix 1 to Part-FCL' / 'Appendix 1 to FCL.110'
        if i + 1 < len(tokens) and tokens[i] == "to" and (
            _DOTTED.match(tokens[i + 1]) or tokens[i + 1] in _KEYWORDS
        ):
            out.extend(tokens[i:i + 2]); i += 2
            if out[-1] in _KEYWORDS and i < len(tokens) and _NUMBERISH.match(tokens[i]):
                out.append(tokens[i]); i += 1
    elif i < len(tokens) and _DOTTED.match(tokens[i]):
        out.append(tokens[i]); i += 1
        # 'AMC1 FCL.940.FI; FCL.940.IRI' - multi-rule references
        while i < len(tokens) and out[-1][-1] in ";,&" and _DOTTED.match(tokens[i]):
            out.append(tokens[i]); i += 1
    # a bare prefix ('GM1') without a rule token is not a ref
    if not out or (len(out) == 1 and _PREFIX.match(out[0])):
        return title.strip(), ""
    return " ".join(out), " ".join(tokens[i:]).lstrip("–—-: ").strip()


def norm_ref(ref: str) -> str:
    return re.sub(r"\s+", "", ref).lower()


def short_type(full: str) -> str:
    first = full.split(";")[0].strip().lower()
    if first.startswith("ir"):
        return "IR"
    if first.startswith("amc"):
        return "AMC"
    if first.startswith("gm"):
        return "GM"
    if first.startswith("cs"):
        return "CS"
    if first.startswith("delegated") or first.startswith("dr ") or "regulation" in first:
        return "IR"
    return "OTHER"


def _type_from_title(title: str, ref: str) -> str:
    """Fallback when EASA left TypeOfContent empty."""
    m = re.match(r"^(?:Appendix \S* ?to )?(AMC|GM|CS)\d*\b", title)
    if m:
        return m.group(1)
    if re.match(r"^(Article|ANNEX|Annex|Appendix)\b", title) or ref != title:
        return "IR"
    return "OTHER"


# --------------------------------------------------------------------------- text

def _run_text(el: etree._Element) -> str:
    parts: list[str] = []
    for node in el.iter():
        tag = node.tag
        if tag == W + "t":
            parts.append(node.text or "")
        elif tag in (W + "tab", W + "ptab"):
            parts.append(" ")
        elif tag in (W + "br", W + "cr"):
            parts.append("\n")
        elif tag == W + "noBreakHyphen":
            parts.append("-")
        elif tag == W + "drawing" or tag == W + "pict":
            parts.append("[figure]")
    return "".join(parts)


def _para_text(p: etree._Element) -> str:
    txt = re.sub(r"[  ]+", " ", _run_text(p)).strip()
    if not txt:
        return ""
    style = p.find(f"{W}pPr/{W}pStyle")
    level = 0
    if style is not None:
        m = re.search(r"ListLevel(\d)", style.get(W + "val", ""))
        if m:
            level = int(m.group(1))
    return "  " * level + txt


def _table_text(tbl: etree._Element) -> str:
    rows = []
    for tr in tbl.findall(f"{W}tr"):
        cells = []
        for tc in tr.findall(f"{W}tc"):
            cell = " ".join(filter(None, (_para_text(p).strip() for p in tc.iter(W + "p"))))
            cells.append(cell)
        if any(cells):
            rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def _sdt_tag(sdt: etree._Element) -> str:
    tag = sdt.find(f"{W}sdtPr/{W}tag")
    return tag.get(W + "val", "") if tag is not None else ""


def _block_text(container: etree._Element, out: list[str], meta: dict) -> None:
    for child in container:
        tag = child.tag
        if tag == W + "p":
            t = _para_text(child)
            if t:
                out.append(t)
        elif tag == W + "tbl":
            t = _table_text(child)
            if t:
                out.append(t)
        elif tag == W + "sdt":
            stag = _sdt_tag(child)
            content = child.find(f"{W}sdtContent")
            if content is None:
                continue
            if stag in ("topic", "heading"):
                continue  # belongs to another topic
            if stag == "Regulatory_x0020_source":
                meta.setdefault("regulatory_source_text", " ".join(
                    filter(None, (_para_text(p) for p in content.iter(W + "p")))))
                continue
            _block_text(content, out, meta)
        elif tag in (W + "customXml", W + "smartTag", W + "ins"):
            _block_text(child, out, meta)


def topic_text(sdt: etree._Element, title: str) -> tuple[str, dict]:
    content = sdt.find(f"{W}sdtContent")
    out: list[str] = []
    meta: dict = {}
    if content is not None:
        _block_text(content, out, meta)
    # first paragraph repeats the topic title
    if out and _squash(out[0]) == _squash(title):
        out = out[1:]
    return "\n".join(out).strip(), meta


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


# --------------------------------------------------------------------------- package

def _open_xml(path: Path) -> IO[bytes]:
    if zipfile.is_zipfile(path):
        zf = zipfile.ZipFile(path)
        names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        if not names:
            raise ValueError(f"{path}: no .xml member in zip")
        return zf.open(max(names, key=lambda n: zf.getinfo(n).file_size))
    return open(path, "rb")


def _load_parts(path: Path) -> tuple[etree._Element, etree._Element]:
    """Stream the package and keep only er:document and w:document."""
    er_doc = w_doc = None
    with _open_xml(path) as fh:
        for _, part in etree.iterparse(fh, events=("end",), tag=PKG_PART, huge_tree=True):
            name = part.get(PKG_NAME, "")
            if name == "/word/document.xml":
                w_doc = part.find(f"pkg:xmlData/{W}document", NS)
                continue
            if er_doc is None and name.lower().startswith("/customxml/item"):  # EASA uses both cases
                found = part.find(f"pkg:xmlData/{ER}document", NS)
                if found is not None:
                    er_doc = found
                    continue
            part.clear()  # images, styles, headers... not needed; free memory
    if er_doc is None or w_doc is None:
        raise ValueError(f"{path}: not an EASA eRules package (er:document or word/document.xml missing)")
    return er_doc, w_doc


def _walk_toc(node: etree._Element, crumbs: list[str]) -> Iterator[tuple[etree._Element, list[str]]]:
    local_crumbs = list(crumbs)
    for child in node:
        if child.tag == ER + "heading":
            title = (child.get("title") or "").strip()
            local_crumbs = crumbs + ([title] if title else [])
        elif child.tag == ER + "topic":
            yield child, local_crumbs
        elif child.tag == ER + "toc":
            yield from _walk_toc(child, local_crumbs)


def parse_book(path: Path | str, code: str) -> ParsedBook:
    path = Path(path)
    er_doc, w_doc = _load_parts(path)
    sdts = {
        s.find(f"{W}sdtPr/{W}id").get(W + "val"): s
        for s in w_doc.iter(W + "sdt")
        if _sdt_tag(s) == "topic" and s.find(f"{W}sdtPr/{W}id") is not None
    }
    book = ParsedBook(code=code, source_title=er_doc.get("source-title", ""), pub_time=er_doc.get("pub-time", ""))
    seq = 0
    for topic, crumbs in _walk_toc(er_doc, []):
        ctype_full = (topic.get("TypeOfContent") or "").strip()
        title = re.sub(r"\s+", " ", topic.get("source-title") or "").strip()
        if ctype_full.rstrip(";").strip().lower() in SKIP_TYPES or title.lower() in FRONTMATTER_TITLES:
            continue
        sdt = sdts.get(topic.get("sdt-id", ""))
        text, meta = topic_text(sdt, title) if sdt is not None else ("", {})
        if not title and not text:
            continue
        if not title:
            title = crumbs[-1] if crumbs else "(untitled)"
        ref, heading = split_ref(title)
        seq += 1
        book.rules.append(Rule(
            erules_id=topic.get("ERulesId", ""),
            book=code,
            seq=seq,
            title=title,
            ref=ref,
            heading=heading,
            content_type=short_type(ctype_full) if ctype_full.strip(" ;") else _type_from_title(title, ref),
            content_type_full=ctype_full.rstrip(";"),
            parent_ir=(topic.get("ParentIR") or "").strip(),
            regulatory_source=(topic.get("RegulatorySource") or meta.get("regulatory_source_text", "")).strip(),
            applicability_date=(topic.get("ApplicabilityDate") or "").strip(),
            entry_into_force_date=(topic.get("EntryIntoForceDate") or "").strip(),
            domain=(topic.get("Domain") or "").strip(";"),
            keywords=(topic.get("Keywords") or "").strip(";"),
            regulated_entity=(topic.get("RegulatedEntity") or "").strip(";"),
            regulatory_subject=(topic.get("RegulatorySubject") or "").strip(";"),
            icao_reference=(topic.get("ICAOReference") or "").strip(";"),
            breadcrumb=" > ".join(crumbs),
            text=text,
        ))
    return book
