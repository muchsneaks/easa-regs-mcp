"""Entrypoint for the hosted connector on Vercel (auto-detected `app`). Locally: uvicorn app:app"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from easa_regs.asgi import app  # noqa: E402

__all__ = ["app"]
