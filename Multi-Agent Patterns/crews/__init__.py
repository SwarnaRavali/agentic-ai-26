"""The same four patterns, built with CrewAI. Same stores, grader, page and Claude bridge as patterns/;
only the framework changes, so the scoreboard compares LangGraph and CrewAI like for like.

  l0_sequential.py   a Crew with Process.sequential: the developer's three tasks
  l1_planned.py      a planner task whose plan is context for a fixed list of worker tasks
  l2_guardrail.py    async scout tasks (in parallel) + a task guardrail as the critic: retry with feedback
  l3_flow.py         a Flow: @start waits for the price feed, @router decides, @listen runs the Level 2 crew
  llm.py             BridgeLLM: CrewAI's BaseLLM → the Claude CLI with a JSON schema (or the script, offline)

CrewAI is optional: pip install -r requirements-crewai.txt
"""
import importlib
import importlib.util
import os
import time
import warnings

# No telemetry or tracing from a teaching demo; set before crewai is imported.
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("CREWAI_TELEMETRY_OPT_OUT", "true")
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

from lab import llm as lab_llm  # noqa: E402  (crews.llm is the CrewAI bridge)
from patterns import common, score, world  # noqa: E402

FILES = {0: "l0_sequential", 1: "l1_planned", 2: "l2_guardrail", 3: "l3_flow"}


def available():
    return importlib.util.find_spec("crewai") is not None


def module(level):
    return importlib.import_module(f"crews.{FILES[level]}")


def run(level, auto_drop=6.0):
    """Run one level end to end. Returns its graded result and its counters, like patterns.run()."""
    if not available():
        raise RuntimeError("CrewAI is not installed: pip install -r requirements-crewai.txt")
    from crewai_core.printer import set_suppress_console_output
    set_suppress_console_output(True)   # the page and search.py draw the run; no CrewAI console panels
    # Task callbacks are closures, so CrewAI warns they can't be checkpointed. This demo doesn't checkpoint crews.
    warnings.filterwarnings("ignore", message="function callbacks cannot be serialized")
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="crewai")   # CrewAI's own internals
    mod = module(level)
    world.reset()
    common.begin(level, mod.TITLE, mod.HUMAN_STEPS, framework="crewai")
    out = mod.run(auto_drop) if level == 3 else mod.run()
    stats = {k: v for k, v in common.stats.items() if k != "t0"}
    stats["seconds"] = round(time.time() - common.stats["t0"], 1)
    result = {"level": level, "framework": "crewai", "brain": lab_llm.MODE if lab_llm.MODE == "offline" else f"{lab_llm.MODE} {lab_llm.MODEL or 'sonnet'}", "title": mod.TITLE, "answer": out.get("answer", ""),
              "grade": score.grade(out.get("pick")), "stats": stats, "world": dict(world.SOURCE)}
    common.emit("run_end", **result)
    return result
