"""Registry of EASA Easy Access Rules (EAR) books the server knows about.

Each book is published by EASA as a zipped Flat-OPC (Word 2003 XML package)
file that embeds an ``er:document`` table of contents with stable ERulesIds.
Download IDs are the numeric part of https://www.easa.europa.eu/en/downloads/<id>/en
and are taken from the book's landing page.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    code: str            # short, stable key used in the DB and tools
    title: str
    xml_download_id: int
    landing_page: str

    @property
    def xml_url(self) -> str:
        return f"https://www.easa.europa.eu/en/downloads/{self.xml_download_id}/en"


BOOKS: dict[str, Book] = {
    b.code: b
    for b in [
        Book(
            code="AIRCREW",
            title="Easy Access Rules for Aircrew (Regulation (EU) No 1178/2011)",
            xml_download_id=136679,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/"
            "easy-access-rules-aircrew-regulation-eu-no-11782011",
        ),
        Book(
            code="AIROPS",
            title="Easy Access Rules for Air Operations (Regulation (EU) No 965/2012)",
            xml_download_id=136682,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/"
            "easy-access-rules-air-operations",
        ),
        Book(
            code="SAILPLANES",
            title="Sailplane Rule Book - Easy Access Rules (Part-SFCL, Part-SAO, ...)",
            xml_download_id=136684,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/"
            "sailplane-rule-book-easy-access-rules",
        ),
        Book(
            code="BALLOONS",
            title="Easy Access Rules for Balloons (Part-BFCL, Part-BOP, ...)",
            xml_download_id=136683,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/easy-access-rules-balloons",
        ),
        Book(
            code="CONTAIR",
            title="Easy Access Rules for Continuing Airworthiness (Part-M, Part-ML, Part-145, Part-CAMO, ...)",
            xml_download_id=136699,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/"
            "easy-access-rules-continuing-airworthiness",
        ),
        Book(
            code="BASIC",
            title="Easy Access Rules for the Basic Regulation (Regulation (EU) 2018/1139)",
            xml_download_id=136659,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/"
            "easy-access-rules-basic-regulation-regulation-eu-20181139",
        ),
        Book(
            code="UAS",
            title="Easy Access Rules for Unmanned Aircraft Systems (drones)",
            xml_download_id=137111,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/"
            "easy-access-rules-unmanned-aircraft-systems",
        ),
        Book(
            code="AERODROMES",
            title="Easy Access Rules for Aerodromes (Regulation (EU) No 139/2014)",
            xml_download_id=136677,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/easy-access-rules-aerodromes",
        ),
        Book(
            code="SERA",
            title="Easy Access Rules for Standardised European Rules of the Air (SERA)",
            xml_download_id=136676,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/"
            "easy-access-rules-standardised-european-rules-air",
        ),
    ]
}

GITHUB_REPO = "muchsneaks/easa-regs-mcp"
INDEX_URL = f"https://github.com/{GITHUB_REPO}/releases/latest/download/easa_regs.sqlite"

DISCLAIMER = (
    "Unofficial reproduction of EASA Easy Access Rules for information only. "
    "Not legally binding - only the texts published in the Official Journal of the EU "
    "are authentic. Always verify against the current official publication "
    "before relying on it for operational or compliance decisions."
)

ATTRIBUTION = "Source: EASA Easy Access Rules (eRules XML), (c) European Union Aviation Safety Agency."
