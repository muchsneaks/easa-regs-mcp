import pytest

from easa_regs.parse import norm_ref, parse_book, short_type, split_ref


@pytest.mark.parametrize("title,ref,heading", [
    ("SERA.5005 Visual flight rules", "SERA.5005", "Visual flight rules"),
    ("AMC1 FCL.740(b) Validity and renewal", "AMC1 FCL.740(b)", "Validity and renewal"),
    ("GM1 SERA.5005(c)(3)(iii)  Visual flight rules", "GM1 SERA.5005(c)(3)(iii)", "Visual flight rules"),
    ("GM1 Article 2(25) Air-taxiing", "GM1 Article 2(25)", "Air-taxiing"),
    ("Article 2 — Definitions", "Article 2", "Definitions"),
    ("Appendix 1 to Part-FCL Crediting", "Appendix 1 to Part-FCL", "Crediting"),
    ("AMC1 ORO.GEN.310(b);(d);(f) Use of aeroplanes", "AMC1 ORO.GEN.310(b);(d);(f)", "Use of aeroplanes"),
    ("AMC1 NCC.IDE.A.120&NCC.IDE.A.125 Operations", "AMC1 NCC.IDE.A.120&NCC.IDE.A.125", "Operations"),
    ("AMC1 FCL.940.FI; FCL.940.IRI Revalidation", "AMC1 FCL.940.FI; FCL.940.IRI", "Revalidation"),
    ("GM1 CS FTL.1.205(d) Flight Duty Period", "GM1 CS FTL.1.205(d)", "Flight Duty Period"),
    ("Multi-pilot operations", "Multi-pilot operations", ""),
    ("Signature", "Signature", ""),
])
def test_split_ref(title, ref, heading):
    assert split_ref(title) == (ref, heading)


def test_norm_and_type():
    assert norm_ref("AMC1 FCL.740(b)") == "amc1fcl.740(b)"
    assert short_type("AMC to IR (Acceptable means of compliance to implementing rule);") == "AMC"
    assert short_type("GM to AMC (Guidance material to acceptable means of compliance);") == "GM"
    assert short_type("IR (Implementing rule);") == "IR"


def test_parse_book(sample_zip):
    book = parse_book(sample_zip, "SERA")
    assert book.pub_time.startswith("2025-08-26")
    refs = [r.ref for r in book.rules]
    assert refs == ["SERA.5005", "AMC1 SERA.5005(c)", "GM1 SERA.5005(c)(3)(iii)", "Article 2"]  # disclaimer skipped
    ir = book.rules[0]
    assert ir.erules_id == "ERULES-1-100"
    assert ir.content_type == "IR"
    assert ir.breadcrumb == "ANNEX: Rules of the Air > SECTION 5 VMC and VFR"
    assert ir.regulatory_source == "Regulation (EU) 2024/404"
    # title paragraph dropped, list levels indented, regulatory-source block excluded, tables rendered
    assert ir.text.splitlines()[0].startswith("(a) Except when operating as a special VFR flight")
    assert "\n  (1) the ceiling is less than 450 m (1 500 ft); or" in ir.text
    assert "| G | 5 km |" in ir.text
    assert "Regulation (EU) 2024/404" not in ir.text
    assert book.rules[1].parent_ir == "SERA.5005 Visual flight rules"
