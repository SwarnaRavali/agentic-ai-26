"""Four patterns, one query, in the browser, built with LangGraph (patterns/) or CrewAI (crews/).

  python -m patterns.server         opens http://127.0.0.1:8701
  python app.py                     the same page, inside the talk (section 4)

The page runs the real graphs or crews in this process and draws the events they emit: the three stores,
the agents and their messages, tool calls, the purchase and its grade. Each run picks its framework and its
brain (scripted, or Claude through the CLI bridge), so the scoreboard compares them side by side.
"""
import argparse
import threading
from pathlib import Path

import crews
import patterns
from lab import claude_cli, llm, web
from patterns import LEVELS, common, live, world

PORT = 8701
FRAMEWORKS = {"langgraph": patterns.run, "crewai": crews.run}


class Session:
    """The current run. One at a time."""

    def __init__(self):
        self.log = web.EventLog()
        self.results = {}                  # (world, framework, level) → last result, for the scoreboard
        self.query = world.QUERY
        self.thread = None
        common.listen(self.emit)

    def emit(self, ev):
        if ev["type"] == "run_start" and ev["query"] != self.query:   # a new query starts a new scoreboard
            self.results, self.query = {}, ev["query"]
        if ev["type"] == "run_end":
            self.results[ev["world"]["kind"], ev["framework"], ev["level"]] = ev
        self.log.add(ev, new_run=ev["type"] == "run_start")

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def launch(self, levels, framework, brain, pace, auto_drop, kind="demo", headless=None, fresh=False, query=None):
        if self.running():
            raise RuntimeError("A run is in progress. Stop it first.")
        if framework == "crewai" and not crews.available():
            raise RuntimeError("CrewAI is not installed: pip install -r requirements-crewai.txt")
        if brain:
            if brain not in llm.BRAINS:
                raise ValueError("unknown brain")
            if llm.BRAINS[brain][0] == "claude" and not claude_cli.available():
                raise RuntimeError("The claude CLI was not found. Install Claude Code, or set CLAUDE_BIN.")
            llm.configure(*llm.BRAINS[brain])
        if query:
            world.parse(query)             # a query without a budget fails here, before the run starts
        common.set_pace(pace)
        common.rearm()
        self.emit({"type": "launched"})      # the page can offer Stop before the first level starts
        self.thread = threading.Thread(target=self._run, args=(levels, FRAMEWORKS[framework], auto_drop, kind, headless, fresh,
                                                               query), daemon=True)
        self.thread.start()

    def _run(self, levels, run, auto_drop, kind, headless, fresh, query):
        try:      # live: collect (or reuse a collection under 15 minutes old) before the first level
            world.use(kind, progress=lambda text: self.emit({"type": "collect", "text": text}), headless=headless, fresh=fresh,
                      query=query, stop=common.cancelled)
        except live.Stopped:
            self.emit({"type": "stopped", "level": levels[0]})
            return
        except Exception as e:
            self.emit({"type": "error", "level": levels[0], "error": f"{type(e).__name__}: {e}"})
            return
        for n in levels:
            if common.cancelled():           # stopped between levels, or before the first one began
                self.emit({"type": "stopped", "level": n})
                return
            try:
                run(n, auto_drop=auto_drop)
            except common.Cancelled:
                self.emit({"type": "stopped", "level": n})
                return
            except Exception as e:   # show it on the page instead of a dead stream
                self.emit({"type": "error", "level": n, "error": f"{type(e).__name__}: {e}"})
                return
        self.emit({"type": "idle"})

    def clear_live(self):
        """Forget the live collection and its scoreboard rows (live and recording)."""
        if self.running():
            raise RuntimeError("A run is in progress. Stop it first.")
        live.forget()
        self.results = {k: v for k, v in self.results.items() if k[0] == "demo"}
        self._blank("live")

    def reset(self):
        """Back to the page as it first opens: no results, the default query, the demo stores.
        The saved live collection stays (clear_live forgets it)."""
        if self.running():
            raise RuntimeError("A run is in progress. Stop it first.")
        self.results = {}
        world.use("demo")
        self.query = world.QUERY
        self._blank("all")

    def _blank(self, what):
        """Every open page reloads with empty panels; the reset event itself is never replayed."""
        self.emit({"type": "reset", "what": what})
        self.log.forget()

    def stop(self):
        if self.running():
            common.cancel()
            world.drop_price()   # wakes a Level 3 watcher that is waiting for the feed


SESSION = Session()


def evidence_page():
    """What the last live collection actually saw: per site, a screenshot and every listing with its verdict."""
    import html
    from datetime import datetime
    ev = live.latest()
    if ev is None:
        return "<!doctype html><meta charset=utf-8><title>Evidence</title><p>No live collection yet. Run a level with World · Live sites.</p>"
    _, listings, sellers, _, _ = world._from_evidence(ev, recorded=True)
    when = datetime.fromisoformat(ev["observed_at"]).astimezone()
    e = html.escape
    rows = "".join(
        f"<tr><td>{e(x['store'])}</td><td><a href='{e(x['url'])}' target=_blank rel=noopener>{e(x['name'])}</a></td>"
        f"<td class=n>₹{x['price']:,}</td><td>{e(x['color'])} · {e(x['type'])}</td><td>{e(x['evidence'])}</td>"
        f"<td class={'ok' if sellers[x['id']]['verified'] else 'no'}>{'verified' if sellers[x['id']]['verified'] else e(sellers[x['id']]['note'])}</td></tr>"
        for x in listings)
    sites = "".join(
        f"<div class=site><h3>{e(s['marketplace'])} <small>{e(s['status'].lower().replace('_', ' '))} · {s['candidate_count']} listings</small></h3>"
        f"<a href='{e(s['search_url'])}' target=_blank rel=noopener>{e(s['search_url'])}</a>"
        f"<img src='evidence/{e(s['marketplace'].lower())}-latest.png' alt='What {e(s['marketplace'])} showed' onerror=\"this.remove()\"></div>"
        for s in ev.get("sources", []))
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Live Evidence</title><style>
:root{{color-scheme:light dark;--bg:#f4f6f8;--fg:#1b1f24;--muted:#5f6b7a;--line:#d6dce4;--ok:#15803d;--no:#b45309}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0e1116;--fg:#e6e9ee;--muted:#94a0b1;--line:#2a313b;--ok:#4ade80;--no:#fbbf24}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,sans-serif}} .w{{max-width:1200px;margin:0 auto;padding:16px}}
h1{{font-size:20px;margin:0 0 4px}} p{{color:var(--muted);margin:0 0 14px}} a{{color:inherit}}
.sites{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin-bottom:16px}}
.site{{border:1px solid var(--line);border-radius:10px;padding:10px;overflow:hidden}} .site h3{{margin:0 0 4px;font-size:15px}}
.site small{{color:var(--muted);font-weight:400}} .site a{{font-size:12px;word-break:break-all;color:var(--muted)}} .site img{{width:100%;margin-top:8px;border-radius:6px}}
table{{width:100%;border-collapse:collapse}} th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}}
th{{font-size:12px;color:var(--muted)}} .n{{text-align:right;font-family:ui-monospace,monospace}} .ok{{color:var(--ok)}} .no{{color:var(--no)}}
</style></head><body><div class=w><h1>Live evidence · {when:%d %b %Y %H:%M}</h1>
<p>{e(ev.get("search_provider", ""))} · {ev.get("duration_ms", 0) / 1000:.0f} s · {len(listings)} listings. Prices are what the page showed, not checkout totals.
Size, stock, delivery and returns are not verified.</p><div class=sites>{sites}</div>
<table><thead><tr><th>Store</th><th>Listing</th><th class=n>Price</th><th>From the evidence</th><th>Seen on</th><th>Verdict</th></tr></thead>
<tbody>{rows}</tbody></table></div></body></html>"""


class Handler(web.Handler):
    page = "patterns.html"
    log = SESSION.log

    def hello(self):
        return {"query": world.QUERY, "default_query": world.DEMO["goal"]["query"], "examples": world.EXAMPLES, "mode": llm.MODE, "model": llm.MODEL or ("sonnet" if llm.MODE == "claude" else ""),
                "results": list(SESSION.results.values()), "running": SESSION.running(), "paused": common.paused(),
                "crewai": crews.available(), "claude": claude_cli.available(),
                "live": live.available(), "recording": live.latest() is not None}

    def get(self, path, query):
        if path == "/evidence":
            self.send(200, evidence_page().encode(), "text/html; charset=utf-8")
            return True
        if path.startswith("/evidence/") and path.endswith(".png"):
            f = live.OUT / path.rsplit("/", 1)[1]
            if f.name in {s["name"].lower() + "-latest.png" for s in live.SITES} and f.exists():
                self.send(200, f.read_bytes(), "image/png")
            else:
                self.json({"error": "not found"}, 404)
            return True
        if path == "/log":                     # the newest run's full log: every event and every model call, one JSON per line
            logs = sorted(common.LOGS.glob("20[0-9][0-9]-*.jsonl")) if common.LOGS.exists() else []
            if logs:
                self.send(200, logs[-1].read_bytes(), "text/plain; charset=utf-8")
            else:
                self.json({"error": "no run yet"}, 404)
            return True
        if path != "/code":
            return False
        q = dict(p.split("=", 1) for p in query.split("&") if "=" in p)
        n = int(q["level"]) if q.get("level", "").isdigit() else -1
        if n not in LEVELS:
            self.json({"error": "no such level"}, 404)
        elif q.get("framework") == "crewai":
            f = Path(crews.__file__).parent / f"{crews.FILES[n]}.py"
            self.json({"file": f"crews/{f.name}", "code": f.read_text(encoding="utf-8")})
        else:
            f = Path(LEVELS[n].__file__)
            self.json({"file": f"patterns/{f.name}", "code": f.read_text(encoding="utf-8")})
        return True

    def post(self, path, body):
        if path == "/run":
            lv = body.get("level", "all")
            levels = sorted(LEVELS) if lv == "all" else [int(lv)]
            if not set(levels) <= set(LEVELS):
                raise ValueError("no such level")
            framework = body.get("framework", "langgraph")
            if framework not in FRAMEWORKS:
                raise ValueError("unknown framework")
            kind = body.get("world", "demo")
            if kind not in ("demo", "live", "recording"):
                raise ValueError("unknown world")
            browser = body.get("browser")
            SESSION.launch(levels, framework, body.get("brain"), min(max(float(body.get("pace", 0.7)), 0), 3),
                           min(max(float(body.get("auto_drop", 8)), 0), 120), kind,
                           headless=None if browser is None else browser == "hidden", fresh=bool(body.get("fresh")),
                           query=(body.get("query") or "").strip()[:200] or None)
        elif path == "/clear-live":
            SESSION.clear_live()
        elif path == "/reset":
            SESSION.reset()
        elif path == "/drop":
            world.drop_price()
        elif path == "/stop":
            SESSION.stop()
        elif path == "/pause":                 # hold a running level at its next step, or let it carry on
            common.pause(bool(body.get("paused")))
            SESSION.emit({"type": "paused", "paused": common.paused()})
        elif path == "/pace":                  # seconds per message; applies to the running level at once
            common.set_pace(min(max(float(body.get("pace", 0.7)), 0), 3))
        else:
            raise LookupError(path)


def make_server(port=PORT):
    return web.make(Handler, port)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    a = p.parse_args()
    url = f"http://127.0.0.1:{a.port}"
    web.serve([make_server(a.port)], url, f"Four patterns: {url}   model: {llm.MODE} {llm.MODEL}", not a.no_browser,
              [SESSION.stop])


if __name__ == "__main__":
    main()
