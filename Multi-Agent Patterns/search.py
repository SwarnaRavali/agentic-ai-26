"""One search query through four coordination patterns. Watch the answer get better.

  python search.py                          all four levels with LangGraph, then the scoreboard
  python search.py --framework crewai       the same four patterns built with CrewAI
  python search.py --framework both         both, compared level by level
  python search.py --level 1 --fast         one level, no pauses
  python search.py --brain claude-haiku     real agents: the Claude Code CLI with your saved login
  python search.py --world live             real listings from Amazon.in, Flipkart and Myntra (opens Chrome)
  python search.py --world recording        the last live collection, replayed
  python search.py --query "Grey running shoes, size 9, under ₹800"     your own query (demo or live)

Query (default): "Black running shoes, size 9, under ₹1,000", end to end to a simulated order. Same stores,
same tools, same model every time.
The code is in patterns/ (LangGraph) and crews/ (CrewAI). Settings come from .env (copy .env.example).
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # ₹ in help and output, even when piped on Windows

import argparse

from rich.panel import Panel
from rich.table import Table

import crews
from lab import llm
from lab.core import console
from patterns import LEVELS, common, run

COLOR = {"task": "cyan", "cfp": "yellow", "bid": "yellow", "award": "cyan", "data": "turquoise2", "flag": "red",
         "ok": "green", "event": "magenta"}
names = {"you": "You", "checkout": "Checkout", "feed": "Price feed"}


def show(ev):
    t = ev["type"]
    if t == "run_start":
        console.print()
        console.print(Panel(f"[bold]{ev['title']}[/]\n[dim]{common_query()}  ·  model: {ev['mode']}"
                            f"{' ' + ev['model'] if ev['model'] else ''}[/]", border_style="cyan", padding=(0, 1)))
    elif t == "agent":
        names[ev["id"]] = ev["label"] + (f" {ev['id'][-1]}" if ev["id"].startswith("scout-") else "")
    elif t == "step":
        console.print(f"\n[bold]— {ev['text']}[/]")
    elif t == "msg":
        k = ev["kind"]
        console.print(f"  [{COLOR[k]}]{k.upper():>5}[/] {names.get(ev['from'], ev['from'])} → "
                      f"{names.get(ev['to'], ev['to'])}: {ev['text']}" + ("  [dim](peer)[/]" if ev.get("peer") else ""))
    elif t == "say":
        style = {"bad": "red", "warn": "yellow", "good": "green"}.get(ev["kind"], "white")
        console.print(f"  [dim]{names.get(ev['id'], ev['id']):>11}[/] [{style}]{ev['text']}[/]")
    elif t == "tool":
        console.print(f"  [dim]{names.get(ev['agent'], ev['agent']):>11} ⚙ {ev['tool']} → {ev['result']}[/]")
    elif t == "note":
        style = {"bad": "red", "warn": "yellow", "good": "green"}.get(ev["kind"], "dim")
        console.print(f"  [{style}]{ev['text']}[/]")
    elif t == "waiting":
        console.print(f"  [dim]Waiting for the price feed (it drops by itself in {ev['auto_drop']:.0f}s)…[/]")
    elif t == "notify":
        console.print(Panel(f"[bold]{ev['title']}[/]\n{ev['text']}", title="Push notification", border_style="yellow"))
    elif t == "run_end":
        g = ev["grade"]
        if not g:
            console.print("[red]Nothing bought.[/]")
            return
        lines = "\n".join(f"{'[green]✓' if ok else '[red]✗'}[/] {k:<19} [dim]{g['why'][k]}[/]" for k, ok in g["checks"].items())
        console.print(Panel(f"[bold]{g['name']} · ₹{g['price']:,}[/]   score {g['score']}/{g['of']}\n{lines}",
                            title="Answer", border_style="green" if g["score"] == g["of"] else "red"))


def common_query():
    from patterns import world
    return world.QUERY


def scoreboard(results):
    t = Table(title="Same query, four patterns")
    for col in ("Level", "Framework", "Answer", "Score", "Agents", "Calls", "Tokens", "Human", "Secs"):
        if col in ("Level", "Answer"):   # only these wrap, so a projector-sized terminal still fits the numbers
            t.add_column(col, ratio=2 if col == "Answer" else 1)
        else:
            t.add_column(col, justify="left" if col in ("Level", "Framework") else "right", no_wrap=True)
    for r in sorted(results, key=lambda r: (r["level"], r["framework"] != "langgraph")):
        g, s = r["grade"], r["stats"]
        level = f"L{r['level']} " + r["title"].split(" · ", 1)[-1]
        framework = {"langgraph": "LangGraph", "crewai": "CrewAI"}[r["framework"]]
        counts = (str(s["agents"]), str(s["llm_calls"]), f"{s['tokens']:,}", str(s["human_steps"]), str(s["seconds"]))
        if not g:
            t.add_row(level, framework, "nothing bought", "—", *counts)
            continue
        color = "green" if g["score"] == g["of"] else "yellow" if g["score"] > 1 else "red"
        t.add_row(level, framework, f"{g['name']} · ₹{g['price']:,}", f"[{color}]{g['score']}/{g['of']}[/]", *counts)
    console.print()
    console.print(t)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--level", type=int, choices=sorted(LEVELS), help="run one level (default: all four)")
    p.add_argument("--fast", action="store_true", help="no pauses between messages")
    p.add_argument("--auto-drop", type=float, default=2.0, help="Level 3: seconds until the price drops")
    p.add_argument("--framework", choices=["langgraph", "crewai", "both"], default="langgraph")
    p.add_argument("--brain", choices=sorted(llm.BRAINS), help="who decides: offline, claude-haiku, claude-sonnet "
                                                           "(default: LAB_LLM / LAB_MODEL from .env)")
    p.add_argument("--world", choices=["demo", "live", "recording"], default="demo",
                   help="demo stores, live sites (collects in Chrome), or the last live recording")
    p.add_argument("--query", help="your own query, with a colour, a type (running or casual), an optional size "
                                   "and a budget (demo stores or live sites)")
    a = p.parse_args()
    from patterns import world
    try:
        print(world.use(a.world, progress=lambda text: console.print(f"[dim]  {text}[/]"), query=a.query)["label"])
    except ValueError as e:
        p.error(str(e))
    if a.brain:
        llm.configure(*llm.BRAINS[a.brain])
    if a.fast:
        common.set_pace(0)
    common.listen(show)
    levels = [a.level] if a.level is not None else sorted(LEVELS)
    runners = {"langgraph": [run], "crewai": [crews.run], "both": [run, crews.run]}[a.framework]
    results = [r(n, auto_drop=a.auto_drop) for n in levels for r in runners]
    if len(results) > 1:
        scoreboard(results)


if __name__ == "__main__":
    main()
