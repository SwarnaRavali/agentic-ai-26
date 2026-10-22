"""Demo 2, the guardrails lab (team, guards, runner, feed, trace, server), and what both demos share:
llm.py (one ask() for every agent), claude_cli.py and web.py.

Importing lab loads settings from .env before any module reads them. Real environment variables win.
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
