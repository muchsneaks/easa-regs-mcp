"""Entry point for the Claude Desktop extension (.mcpb, uv runtime)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from easa_regs.server import main  # noqa: E402

if __name__ == "__main__":
    main()
