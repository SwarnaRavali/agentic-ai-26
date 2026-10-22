"""What every level shares: the event stream the terminal and the browser show, and think(), the one LLM call.

Agents don't print. They emit events (an agent appears, a message flies, a task changes) and whoever is
listening draws them: search.py prints them with rich, patterns/server.py streams them to the browser.
"""
import json
import os
import threading
import time
from datetime import datetime

from lab import llm, trace

PACE = float(os.getenv("LAB_DELAY", "0.7"))   # seconds per message, so the room can follow
_listeners = []
_lock = threading.Lock()
stats = {}
_cancel = threading.Event()
_resume = threading.Event()   # cleared while a run is paused
_resume.set()
LOGS = trace.OUTPUT / "patterns"   # one JSONL file per run: every event the page saw, plus every model call in full
KEEP_LOGS = 30
_log = None


class Cancelled(Exception):
    """Raised inside the running graph when someone presses Stop."""


def cancel():
    _cancel.set()
    _resume.set()


def cancelled():
    return _cancel.is_set()


def rearm():
    """A new launch: forget the last Stop. Not in begin(), so a Stop pressed while a run is still starting
    (CrewAI loading, a live collection) holds."""
    _cancel.clear()


def pause(on):
    """Pause a running level at its next event (the page's ❚❚ Pause); resume where it stopped."""
    _resume.clear() if on else _resume.set()


def paused():
    return not _resume.is_set()


def set_pace(seconds):
    global PACE
    PACE = seconds


def listen(fn):
    _listeners.append(fn)
    return lambda: _listeners.remove(fn)


def emit(event, pause=0.0, **data):
    while not _resume.wait(0.2):              # paused: hold here; Stop still works
        if _cancel.is_set():
            break
    if _cancel.is_set():
        raise Cancelled()
    with _lock:
        if event == "msg":
            stats["messages"] += 1
        if event == "agent" and data.get("role") not in ("user", "infra"):
            stats["agents"] += 1
        _send(event, data)
    if pause and PACE:
        time.sleep(PACE * pause)


def _send(event, data):
    """Hand one event to every listener and the run log. Call with _lock held."""
    global _log
    ev = {"type": event, "t": round(time.time() - stats.get("t0", time.time()), 2), **data}
    for fn in list(_listeners):
        fn(ev)
    if _log:
        _log.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
        _log.flush()
        if event == "run_end":
            _log.close()
            _log = None


def _model_call(kind, data):
    """lab.llm reports every model call to trace; put it on the bus too, so the page's Run log shows the raw exchange.
    Not through emit(): this runs inside the call, and Stop or Pause must not break it halfway."""
    if kind in ("llm", "llm_error") and "t0" in stats:
        with _lock:
            _send(kind, data)


trace.listeners.append(_model_call)


def log_path():
    return _log.name if _log else None


def _open_log(level, framework):
    global _log
    if _log:
        _log.close()
    from patterns import world
    trace.prune(LOGS, "20[0-9][0-9]-*.jsonl", KEEP_LOGS - 1)
    LOGS.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    name = f"{now:%Y-%m-%d_%H-%M-%S}-{now.microsecond // 1000:03d}_{framework}_L{level}_{world.SOURCE.get('kind', 'demo')}.jsonl"
    _log = open(LOGS / name, "w", encoding="utf-8")


def begin(level, title, human_steps, framework="langgraph"):
    """Reset the counters for a new run."""
    llm.reset()
    _resume.set()
    stats.clear()
    stats.update(level=level, agents=0, messages=0, tokens=0, llm_calls=0, human_steps=human_steps, t0=time.time())
    from patterns import score, world
    with _lock:
        _open_log(level, framework)
    emit("run_start", level=level, framework=framework, title=title, mode=llm.MODE, model=llm.MODEL, human_steps=human_steps,
         query=world.QUERY, checks=score.names(), listings=world.view(), stores=list(world.STORES), world=dict(world.SOURCE))


# Shorthands for the events the UI draws. Each one is a single emit().
def agent(id, label, role="agent", **o):
    emit("agent", id=id, label=label, role=role, **o)


def status(id, state, text=""):
    emit("status", id=id, state=state, text=text)


def msg(a, b, type, text, **o):
    emit("msg", pause=1, **{"from": a, "to": b, "kind": type, "text": text, **o})


def say(id, text, kind=""):
    emit("say", pause=0.6, id=id, text=text, kind=kind)


def note(text, kind="sys"):
    emit("note", pause=0.4, text=text, kind=kind)


def listing(ids, state, note=""):
    """Light up listings in the page's store panel: checked, kept, out, pick, rejected, bought."""
    emit("listing", pause=0.15, ids=[ids] if isinstance(ids, str) else list(ids), state=state, note=note)


def step(text):
    emit("step", pause=0.3, text=text)


def tool(agent_id, name, args, result):
    emit("tool", pause=0.3, agent=agent_id, tool=name, args=args, result=result)


def think(agent_id, role, context, actions, offline, fields=None):
    """One LLM call. Offline (or if the model fails) it returns the scripted reply, so the run always finishes."""
    status(agent_id, "active", "thinking…")
    reply, tokens = llm.ask(agent_id, role, context, actions, offline=offline, fields=fields)
    with _lock:
        stats["tokens"] += tokens
        stats["llm_calls"] += 1
    emit("tokens", agent=agent_id, tokens=tokens, total=stats["tokens"], llm=llm.last())
    return reply


def counted(agent_id, tokens):
    """Count a model call made elsewhere (the CrewAI bridge) and tell the page who answered."""
    with _lock:
        stats["tokens"] += tokens
        stats["llm_calls"] += 1
    emit("tokens", agent=agent_id, tokens=tokens, total=stats["tokens"], llm=llm.last())
