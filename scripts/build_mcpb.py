"""Assemble and pack the Claude Desktop extension (dist/easa-regs.mcpb).

Uses the MCPB uv runtime: Claude Desktop installs Python + dependencies itself,
so users need nothing but a double-click. Requires Node (npx) for `mcpb pack`.

    python scripts/build_mcpb.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build" / "mcpb"
DIST = ROOT / "dist"

TOOLS = [
    ("search_easa_rules", "Search the EASA Easy Access Rules (natural language, rule references, German terms)."),
    ("get_easa_rule", "Full text of one rule with citation, legal type (IR/AMC/GM/CS) and linked AMC/GM."),
    ("browse_easa_toc", "Structure of a regulation book; list every rule of a subpart."),
    ("list_easa_sources", "Indexed books with their EASA publication dates."),
]


def main() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    version = project["version"]

    shutil.rmtree(BUILD, ignore_errors=True)
    (BUILD / "src").mkdir(parents=True)
    shutil.copytree(ROOT / "src" / "easa_regs", BUILD / "src" / "easa_regs",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy(ROOT / "mcpb" / "server_main.py", BUILD / "server_main.py")
    shutil.copy(ROOT / "mcpb" / "icon.png", BUILD / "icon.png")
    shutil.copy(ROOT / "LICENSE", BUILD / "LICENSE")

    # uv "virtual" project: dependencies only, the package is imported from src/ by server_main.py
    deps = ",\n".join(f'    "{d}"' for d in project["dependencies"])
    (BUILD / "pyproject.toml").write_text(
        f'[project]\nname = "easa-regs-mcpb"\nversion = "{version}"\n'
        f'requires-python = "{project["requires-python"]}"\ndependencies = [\n{deps},\n]\n'
    )
    (BUILD / ".mcpbignore").write_text(".venv/\n__pycache__/\n*.pyc\n")

    manifest = {
        "manifest_version": "0.4",
        "name": "easa-regs",
        "display_name": "EASA Regs",
        "version": version,
        "description": "Search and cite EASA aviation regulations (Part-FCL, Air OPS, SERA, Part-ML ...) with exact references.",
        "long_description": (
            "Gives Claude direct access to 9,000+ rules from the official EASA Easy Access Rules: Aircrew "
            "(Part-FCL, MED, ARA, ORA, DTO), Air Operations (ORO, CAT, NCO, NCC, SPO, SPA), SERA, Sailplanes, "
            "Balloons, Continuing Airworthiness (Part-M, ML, 145, CAMO), Basic Regulation, UAS and Aerodromes. "
            "Every answer can quote the original text with rule reference, legal type (IR/AMC/GM) and revision. "
            "The index updates itself weekly. Unofficial and not legally binding."
        ),
        "author": {"name": "easa-regs", "url": "https://github.com/muchsneaks/easa-regs-mcp"},
        "homepage": "https://easa-regs-site.vercel.app/",
        "documentation": "https://github.com/muchsneaks/easa-regs-mcp#readme",
        "support": "https://github.com/muchsneaks/easa-regs-mcp/issues",
        "repository": {"type": "git", "url": "https://github.com/muchsneaks/easa-regs-mcp"},
        "icon": "icon.png",
        "server": {
            "type": "uv",
            "entry_point": "server_main.py",
            "mcp_config": {"command": "uv", "args": ["run", "--directory", "${__dirname}", "server_main.py"]},
        },
        "tools": [{"name": n, "description": d} for n, d in TOOLS],
        "compatibility": {"platforms": ["darwin", "win32", "linux"], "runtimes": {"python": project["requires-python"]}},
        "keywords": ["easa", "aviation", "regulations", "part-fcl", "pilot", "sera", "air-ops"],
        "license": "MIT",
    }
    (BUILD / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    DIST.mkdir(exist_ok=True)
    out = DIST / "easa-regs.mcpb"
    npx = shutil.which("npx")
    if not npx:
        sys.exit("npx not found - install Node.js to pack the bundle")
    subprocess.run([npx, "-y", "@anthropic-ai/mcpb", "validate", str(BUILD / "manifest.json")], check=True)
    subprocess.run([npx, "-y", "@anthropic-ai/mcpb", "pack", str(BUILD), str(out)], check=True)
    print(f"Built {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
