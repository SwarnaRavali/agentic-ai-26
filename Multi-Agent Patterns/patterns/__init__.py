"""One shopping query, four coordination patterns. Same tools, same stores, same LLM; only the pattern changes.

  python search.py              all four levels, then the scoreboard
  python search.py --level 2    one level
  python app.py                 the same runs in the browser, inside the talk

  l0_pipeline.py       Level 0 · scripted pipeline       fixed hand-offs
  l1_orchestrator.py   Level 1 · orchestrator → workers  hub and spoke
  l2_team.py           Level 2 · team + critic           fan out / fan in, critic, rework loop
  l3_event.py          Level 3 · event-driven            publish/subscribe, then the Level 2 team
  score.py             the grader, the same for every level
"""
import time

from lab import llm
from patterns import common, l0_pipeline, l1_orchestrator, l2_team, l3_event, score, world

LEVELS = {0: l0_pipeline, 1: l1_orchestrator, 2: l2_team, 3: l3_event}


def run(level, auto_drop=6.0):
    """Run one level end to end. Returns its graded result and its counters."""
    mod = LEVELS[level]
    world.reset()
    common.begin(level, mod.TITLE, mod.HUMAN_STEPS)
    out = mod.run(auto_drop) if level == 3 else mod.run()
    stats = {k: v for k, v in common.stats.items() if k != "t0"}
    stats["seconds"] = round(time.time() - common.stats["t0"], 1)
    result = {"level": level, "framework": "langgraph", "brain": llm.MODE if llm.MODE == "offline" else f"{llm.MODE} {llm.MODEL or 'sonnet'}", "title": mod.TITLE, "answer": out.get("answer", ""),
              "grade": score.grade(out.get("pick")), "stats": stats, "world": dict(world.SOURCE)}
    common.emit("run_end", **result)
    return result
