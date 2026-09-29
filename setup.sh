#!/usr/bin/env bash
# One-shot setup: venv, install, download EASA XML (if missing), build index, run tests,
# and optionally register the server in Claude Desktop.
set -euo pipefail
cd "$(dirname "$0")"

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
    PY="$(command -v "$c")"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python >= 3.10 needed. Install it with:  brew install python@3.12   (or from python.org)"; exit 1
fi
echo "Using $PY ($("$PY" --version))"

[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e ".[dev]"

for b in $(.venv/bin/python -c "from easa_regs.sources import BOOKS; print(' '.join(BOOKS))"); do
  [ -f "data/raw/$b.zip" ] || .venv/bin/easa-regs-fetch "$b"
done
.venv/bin/easa-regs-build
.venv/bin/pytest -q

BIN="$(pwd)/.venv/bin/easa-regs-mcp"
CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
echo
echo "Server ready: $BIN"
read -r -p "Register it in Claude Desktop ($CFG)? [y/N] " yn
if [[ "$yn" =~ ^[Yy]$ ]]; then
  mkdir -p "$(dirname "$CFG")"
  [ -f "$CFG" ] && cp "$CFG" "$CFG.bak.$(date +%s)"
  "$PY" - "$CFG" "$BIN" <<'EOF'
import json, sys, pathlib
cfg, binary = pathlib.Path(sys.argv[1]), sys.argv[2]
data = json.loads(cfg.read_text()) if cfg.exists() and cfg.read_text().strip() else {}
data.setdefault("mcpServers", {})["easa-regs"] = {"command": binary}
cfg.write_text(json.dumps(data, indent=2))
print("Added 'easa-regs'. Quit and reopen Claude Desktop (Cmd+Q) to load it.")
EOF
else
  echo "Add manually under \"mcpServers\":  \"easa-regs\": {\"command\": \"$BIN\"}"
fi
