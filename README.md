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

**Website with one-click setup:** https://easa-regs-site.vercel.app/

| Where | How |
|---|---|
| **Claude (web, desktop, iOS, Android)** | *Customize › Connectors › + › Add custom connector*, paste the hosted URL (see website). Works on the Free plan too. |
| **Claude Desktop, local** | Download [`easa-regs.mcpb`](https://github.com/muchsneaks/easa-regs-mcp/releases/latest/download/easa-regs.mcpb), double-click, *Install*. No Python needed. |
| **Claude Code** | `claude mcp add easa-regs -- uvx --from git+https://github.com/muchsneaks/easa-regs-mcp easa-regs-mcp` |
| **Any MCP client** | `{"command": "uvx", "args": ["--from", "git+https://github.com/muchsneaks/easa-regs-mcp", "easa-regs-mcp"]}` |

The first start downloads the prebuilt index (~33 MB) from the latest release and refreshes it weekly.

### Host the remote connector yourself

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/muchsneaks/easa-regs-mcp)
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/muchsneaks/easa-regs-mcp)

**Vercel / serverless:** `app.py` exposes a lifespan-free ASGI app (`easa_regs.asgi:app`). It downloads the
prebuilt index to `/tmp` on first use and refreshes it daily, so no build step or redeploy is needed.
Locally: `uvicorn app:app --port 8000`.

**Docker host:** `docker build -t easa-regs-mcp . && docker run -p 8000:8000 easa-regs-mcp`.
The MCP endpoint is `https://<your-host>/mcp` (stateless streamable HTTP), health check at `/health`.
Optional `ALLOWED_HOSTS=your.domain` enables DNS-rebinding protection.

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
  asgi.py      serverless ASGI app for the hosted connector
mcpb/          Claude Desktop extension (built by scripts/build_mcpb.py, attached to every release)
app.py, vercel.json       hosted connector on Vercel (serverless)
Dockerfile, render.yaml   hosted connector on any Docker host
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
