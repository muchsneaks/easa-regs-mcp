"""Builds a tiny synthetic eRules package that mirrors EASA's real structure."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _topic(sdt_id: str, title: str, paras: list[tuple[str, int]], table: list[list[str]] | None = None) -> str:
    body = f'<w:p><w:pPr><w:pStyle w:val="Heading3IR"/></w:pPr><w:r><w:t>{title}</w:t></w:r></w:p>'
    body += (
        '<w:sdt><w:sdtPr><w:tag w:val="Regulatory_x0020_source"/><w:id w:val="1"/></w:sdtPr><w:sdtContent>'
        '<w:p><w:r><w:t>Regulation (EU) 2024/404</w:t></w:r></w:p></w:sdtContent></w:sdt>'
    )
    for text, level in paras:
        body += (f'<w:p><w:pPr><w:pStyle w:val="ListLevel{level}"/></w:pPr>'
                 f'<w:r><w:t>{text.split(" ", 1)[0]}</w:t></w:r><w:r><w:tab/><w:t>{text.split(" ", 1)[1]}</w:t></w:r></w:p>')
    if table:
        body += "<w:tbl>" + "".join(
            "<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>" for c in row) + "</w:tr>"
            for row in table) + "</w:tbl>"
    return (f'<w:sdt><w:sdtPr><w:alias w:val="topic"/><w:tag w:val="topic"/><w:id w:val="{sdt_id}"/></w:sdtPr>'
            f"<w:sdtContent>{body}</w:sdtContent></w:sdt>")


def _meta(sdt_id: str, title: str, erid: str, ctype: str, parent: str = "") -> str:
    return (f'<er:topic sdt-id="{sdt_id}" source-title="{title}" ERulesId="{erid}" Domain="Air operations;" '
            f'ApplicabilityDate="01 May, 2025" EntryIntoForceDate="01 May, 2024" Keywords="" '
            f'RegulatedEntity="Flight crew;" RegulatorySource="Regulation (EU) 2024/404" RegulatorySubject="" '
            f'ICAOReference="Annex 2;" TypeOfContent="{ctype}" ParentIR="{parent}" />')


PACKAGE = f"""<?xml version="1.0" encoding="utf-8"?>
<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage">
 <pkg:part pkg:name="/customXml/item1.xml"><pkg:xmlData><junk/></pkg:xmlData></pkg:part>
 <pkg:part pkg:name="/customXml/item9.xml"><pkg:xmlData>
  <er:document xmlns:er="http://www.easa.europa.eu/erules-export" source-title="Easy Access Rules for Testing"
      pub-time="2025-08-26T11:54:00Z">
   <er:toc>
    {_meta("10", "Disclaimer", "ERULES-1-1", "Disclaimer;")}
    <er:heading sdt-id="20" title="ANNEX: Rules of the Air"/>
    <er:toc>
     <er:heading sdt-id="21" title="SECTION 5 VMC and VFR"/>
     {_meta("100", "SERA.5005 Visual flight rules", "ERULES-1-100", "IR (Implementing rule);")}
     {_meta("101", "AMC1 SERA.5005(c)  Visual flight rules", "ERULES-1-101",
            "AMC to IR (Acceptable means of compliance to implementing rule);", "SERA.5005 Visual flight rules")}
     {_meta("102", "GM1 SERA.5005(c)(3)(iii) Visual flight rules", "ERULES-1-102",
            "GM to IR (Guidance material to implementing rule);", "SERA.5005 Visual flight rules")}
     {_meta("103", "Article 2 Definitions", "ERULES-1-103", "IR (Implementing rule);")}
    </er:toc>
   </er:toc>
  </er:document></pkg:xmlData></pkg:part>
 <pkg:part pkg:name="/word/document.xml"><pkg:xmlData>
  <w:document xmlns:w="{W}"><w:body>
   {_topic("10", "Disclaimer", [("(a) Not legally binding.", 0)])}
   {_topic("100", "SERA.5005 Visual flight rules",
           [("(a) Except when operating as a special VFR flight, VFR flights shall be conducted in VMC.", 0),
            ("(1) the ceiling is less than 450 m (1 500 ft); or", 1)],
           table=[["Airspace class", "Flight visibility"], ["G", "5 km"]])}
   {_topic("101", "AMC1 SERA.5005(c)  Visual flight rules", [("(a) Night VFR should be planned carefully.", 0)])}
   {_topic("102", "GM1 SERA.5005(c)(3)(iii) Visual flight rules", [("(a) Guidance on mountainous terrain.", 0)])}
   {_topic("103", "Article 2 Definitions", [("(1) aerodrome means a defined area.", 0)])}
  </w:body></w:document></pkg:xmlData></pkg:part>
 <pkg:part pkg:name="/word/media/image1.png"><pkg:binaryData>AAAA</pkg:binaryData></pkg:part>
</pkg:package>"""


@pytest.fixture(scope="session")
def sample_zip(tmp_path_factory) -> Path:
    p = tmp_path_factory.mktemp("raw") / "SERA.zip"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Easy Access Rules for Testing.xml", PACKAGE)
    return p


@pytest.fixture()
def sample_db(sample_zip, tmp_path, monkeypatch):
    from easa_regs import db
    from easa_regs.parse import parse_book

    path = tmp_path / "t.sqlite"
    con = db.connect(path)
    db.store_book(con, parse_book(sample_zip, "SERA"))
    monkeypatch.setenv("EASA_REGS_DB", str(path))
    from easa_regs import server
    server._con.cache_clear()
    yield con
    server._con.cache_clear()
