"""The whole session in one command: the talk, with the live demo running inside it.

  python app.py                     opens http://127.0.0.1:8700
  python app.py --no-browser
  LAB_LLM=claude python app.py      start with Claude as the brain (the page can switch per run)

Two local servers:
  8700  web/talk.html       the talk: 1 patterns · 2 LangGraph · 3 CrewAI · 4 live demo
  8701  patterns.server     the live demo (section 4), also on its own page
The guardrails lab runs on its own: python -m lab.server, or python run.py.
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # ₹ in help and output, even when piped on Windows

import argparse  # noqa: E402

from lab import llm, web  # noqa: E402
from patterns import server as patterns_server  # noqa: E402


class Talk(web.Handler):
    page = "talk.html"
    log = web.EventLog()   # the talk itself streams nothing


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=8700, help="the talk")
    p.add_argument("--live-port", type=int, default=patterns_server.PORT, help="the live demo")
    p.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    a = p.parse_args()
    servers = [web.make(Talk, a.port), patterns_server.make_server(a.live_port)]
    url = f"http://127.0.0.1:{a.port}/?live={a.live_port}"
    web.serve(servers, url, f"Talk: {url}\nLive demo: http://127.0.0.1:{a.live_port}\nModel: {llm.MODE} {llm.MODEL}",
              not a.no_browser, [patterns_server.SESSION.stop])


if __name__ == "__main__":
    main()
