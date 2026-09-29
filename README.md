# easa-regs-mcp

**Give Claude (or any MCP client) the EASA rulebook.** Search, read and cite the EASA Easy Access Rules with
exact references instead of half-remembered answers.

> *"What do I need to revalidate my SEP class rating by experience?"*
> Claude calls `search_easa_rules`, reads **FCL.740.A**, and answers quoting (b)(1)(ii): 12 hours in class within
> 12 months incl. 6 h PIC, 12 take-offs and landings and 1 h refresher training with an FI/CRI, plus the linked AMC/GM.

Built by a CPL(A)/IR flight instructor who got tired of scrolling 1,500-page PDFs.

## Coverage

| Book | Contents |
|---|---|
| `AIRCREW` | Part-FCL, Part-MED, Part-CC, Part-ARA, Part-ORA, Part-DTO |
| `AIROPS` | Part-ORO, CAT, NCO, NCC, SPO, SPA, IAM, CS-FTL |
| `SERA` | Standardised European Rules of the Air |
| `SAILPLANES` | Sailplane Rule Book (Part-SFCL, Part-SAO, ...) |
| `BALLOONS` | Part-BFCL, Part-BOP, ... |
| `CONTAIR` | Continuing airworthiness: Part-M, Part-ML, Part-145, Part-CAMO, Part-CAO |
| `BASIC` | Basic Regulation (EU) 2018/1139 |
| `UAS` | Drones (Regulations (EU) 2019/947 and 2019/945) |
| `AERODROMES` | Regulation (EU) No 139/2014 |

Every rule keeps its stable EASA `ERulesId`, type (**IR** binding / **AMC** / **GM** / **CS**), location in the
regulation, amending regulation, applicability date and its linked AMC/GM. Tables and list structure are preserved.
The index is rebuilt weekly from EASA's official XML by a GitHub Action and published as a release.

## Tools

| Tool | Purpose |
|---|---|
| `search_easa_rules(query, book?, content_type?, limit?)` | Ranked search. Understands rule refs (`FCL.740`), plain English, common abbreviations (SEP, TMG, PIC, SVFR...) and common German terms. When an AMC/GM matches, its parent IR is shown first. |
| `get_easa_rule(ref, book?, include_related?, max_chars?)` | Full text, citation, metadata, parent IR and all AMC/GM. Accepts `FCL.740.A`, `AMC1 FCL.740(b)`, `sera.5010` or an ERulesId. |
| `browse_easa_toc(book, section_contains?)` | Book structure with IR/AMC/GM counts; lists all rules of a subpart (e.g. `"SUBPART H"`). |
| `list_easa_sources()` | Indexed books, publication dates, disclaimer. |

## Install

Needs Python 3.10+. The first start downloads the prebuilt index (~25 MB) from the latest release.

**Claude Desktop** (Settings > Developer > Edit Config), using [uv](https://docs.astral.sh/uv/):

```json
{
  "mcpServers": {
    "easa-regs": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/muchsneaks/easa-regs-mcp", "easa-regs-mcp"]
    }
  }
}
```

**Claude Code:** `claude mcp add easa-regs -- uvx --from git+https://github.com/muchsneaks/easa-regs-mcp easa-regs-mcp`

**Remote / hosted** (streamable HTTP at `/mcp`): `easa-regs-mcp --http --host 0.0.0.0 --port 8000`

## Develop / build the index yourself

```bash
git clone https://github.com/muchsneaks/easa-regs-mcp && cd easa-regs-mcp
./setup.sh      # venv, install, download EASA XML, build index, run tests, optional Claude Desktop registration
```

or step by step: `pip install -e ".[dev]" && easa-regs-fetch && easa-regs-build && pytest -q`.
`python tests/eval_questions.py` prints the retrieval hit rate on 30 real pilot/instructor questions.

```
src/easa_regs/
  sources.py   books, EASA download IDs, disclaimer
  fetch.py     download EASA XML zips / the prebuilt index (stdlib only)
  parse.py     EASA eRules XML (Flat OPC + er: metadata) -> rule records
  db.py        SQLite FTS5 index, search + rerank, lookup, AMC/GM links
  build.py     parse + index + manifest.json
  server.py    FastMCP server (stdio or streamable HTTP)
```

If EASA changes a download link, update the ID in `sources.py` (the number in
`https://www.easa.europa.eu/en/downloads/<id>/en` on the book's page).

## Limitations

- Unofficial and **not legally binding**. Only the texts in the Official Journal of the EU are authentic.
  Always verify before operational or compliance decisions.
- National rules (e.g. LBA, NfL, AIP), ICAO documents and operator manuals are not included.
- The smallest unit is an EASA "topic" (one rule with all its paragraphs).
- Future-applicable versions are not yet separated from current ones.

## Licence

Code: MIT. Content: EASA Easy Access Rules, (c) European Union Aviation Safety Agency - "Reproduction is
authorised, provided the source is acknowledged" ([EASA copyright notice](https://www.easa.europa.eu/en/copyright-disclaimer)).
The server includes the attribution and disclaimer in its responses.
