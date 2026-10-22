"""Run the agent team end to end. Used by run.py (terminal) and lab/server.py (browser).

run()      one run: a price drop starts the team
resume()   carry on the last run from its last checkpoint (after a crash)
history()  list the last run's checkpoints
rewind(n)  replay the last run from checkpoint n, optionally with different guardrails
"""
import json
import os
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.errors import GraphRecursionError
from langgraph.types import Command
from rich.prompt import Prompt
from rich.table import Table

from lab import feed, llm, team, trace
from lab.core import console, header, note, say, summary

RECURSION_LIMIT = 24   # LangGraph's own safety net (default is 25)
CHECKPOINTS = trace.OUTPUT / "checkpoints.sqlite"
LAST = trace.OUTPUT / "last_run.json"


def run(owner=True, budget=True, approval=True, chaos=False, watch=False, auto_drop=None, answer=None,
        crash_after=None):
    """One run. owner/budget/approval switch the guardrails; chaos makes the owner re-check forever.

    watch:       wait for a price change in the feed instead of firing at once
    auto_drop:   seconds until the price drops by itself
    answer:      "approve" or "deny" without asking; None asks the human
    crash_after: kill the process right after this node, to show resume()
    """
    llm.reset()
    guards = {"owner": owner, "budget": budget, "approval": approval}
    off = [g for g, on in guards.items() if not on]
    label = ("no-" + "-no-".join(off) if off else "safe") + ("-chaos" if chaos else "")
    rec = trace.Run(label, {"guards": guards, "chaos": chaos, "watch": watch, "auto_drop": auto_drop,
                            "answer": answer, "crash_after": crash_after})
    _remember(rec.dir.name, guards, chaos)
    header("Run", "The agent team" + (f"  [red](guardrails off: {', '.join(off)})[/]" if off else ""),
           "A price drop starts the team. Scouts check every store in parallel, an evaluator picks, one agent buys."
           + ("  [red](--chaos)[/]" if chaos else ""))
    try:
        event = get_event(watch or auto_drop is not None, auto_drop)
    except BaseException as e:   # Ctrl+C while waiting for the price to drop
        rec.close(console, {}, ended=f"{type(e).__name__} before the price dropped")
        raise
    return _drive({"event": event}, _config(rec.dir.name, guards, chaos), rec, answer, crash_after)


def resume(answer=None):
    """Carry on the last run from its last saved checkpoint. Nodes that already finished don't run again."""
    llm.reset()
    last = _last()
    graph = _graph()
    config = _config(last["thread"], last["guards"], last["chaos"])
    snap = graph.get_state(config)
    rec = trace.Run("resume", {"thread": last["thread"]})
    header("Resume", f"Resuming {last['thread']}", "From the last checkpoint. Finished agents don't run again.")
    if not snap.next:
        note("That run already finished. Nothing to resume.", "yellow")
        rec.close(console, snap.values)
        return snap.values, rec.dir
    done = [n for n in ("watcher", "scout", "evaluator") if n not in snap.next and _ran(graph, config, n)]
    note(f"Already done, not re-run: {', '.join(done) or 'nothing'}. Next: {', '.join(snap.next)}.", "green")
    rec.event("resume_from", thread=last["thread"], next=list(snap.next), done=done)
    rec.prev = snap.values
    return _drive(None, config, rec, answer, None, graph)


def history(show=True):
    """The last run's checkpoints, oldest first: [(n, snapshot)]."""
    last = _last()
    graph = _graph()
    snaps = list(reversed(list(graph.get_state_history(_config(last["thread"], last["guards"], last["chaos"])))))
    if show:
        t = Table(title="Checkpoints of the last run", caption=last["thread"], title_justify="left")
        for col in ("#", "before", "turn", "tokens", "owner", "cart"):
            t.add_column(col)
        for n, s in enumerate(snaps):
            v = s.values
            t.add_row(str(n), ", ".join(s.next) or "(end)", str(v.get("turn", 0)), f"{v.get('tokens', 0):,}",
                      str(v.get("owner") or "—"), str(len(v.get("cart", []))))
        console.print(t)
    return list(enumerate(snaps))


def rewind(n, owner=True, budget=True, approval=True, chaos=False, answer=None):
    """Replay the last run from checkpoint n, with these guardrails. Everything before n is reused, not re-run."""
    llm.reset()
    last = _last()
    snaps = dict(history(show=False))
    if n not in snaps:
        raise SystemExit(f"No checkpoint #{n}. See: python run.py --history")
    snap = snaps[n]
    guards = {"owner": owner, "budget": budget, "approval": approval}
    rec = trace.Run(f"rewind{n}", {"thread": last["thread"], "checkpoint": n, "guards": guards, "chaos": chaos})
    _remember(last["thread"], guards, chaos)
    off = [g for g, on in guards.items() if not on]
    header("Rewind", f"Back to checkpoint #{n}, before: {', '.join(snap.next) or 'the end'}",
           "Same event, same offers. Nothing before this point runs again."
           + (f"  Guardrails off: {', '.join(off)}" if off else "  All guardrails on."))
    config = _config(last["thread"], guards, chaos)
    config["configurable"]["checkpoint_id"] = snap.config["configurable"]["checkpoint_id"]
    rec.prev = snap.values
    return _drive(None, config, rec, answer, None)


def get_event(watch, auto_drop):
    feed.reset_feed()
    goal = feed.GOAL
    note(f"Saved goal: {goal['item']} under ₹{goal['max_price']:,}. Mode: {llm.MODE}.")
    if watch:
        how = f"auto drop in {auto_drop}s" if auto_drop is not None else \
              "run in a second terminal: python run.py --drop"
        console.print(f"[magenta]{'Watcher':>9}[/] [bold]WATCHING[/]     store feed… nobody is typing ({how})")
        event = feed.watch(auto_drop=auto_drop)
        trace.event("trigger", source="watch", event=event)
        return event
    before = feed.read_feed()
    feed.drop_price()
    event = feed.find_event(before, feed.read_feed())
    trace.event("trigger", source="drop_price", event=event)
    return event


# ---------------------------------------------------------------- internals

def _graph():
    trace.OUTPUT.mkdir(exist_ok=True)
    return team.build(SqliteSaver(sqlite3.connect(CHECKPOINTS, check_same_thread=False)))


def _config(thread, guards, chaos):
    return {"recursion_limit": RECURSION_LIMIT,
            "configurable": {"thread_id": thread, "guards": guards, "chaos": chaos}}


def _remember(thread, guards, chaos):
    trace.OUTPUT.mkdir(exist_ok=True)
    LAST.write_text(json.dumps({"thread": thread, "guards": guards, "chaos": chaos}), encoding="utf-8")


def _last():
    if not LAST.exists():
        raise SystemExit("No earlier run. Start one first: python run.py")
    return json.loads(LAST.read_text(encoding="utf-8"))


def _ran(graph, config, node):
    return any(node in (s.next or ()) for s in graph.get_state_history(config))


def _drive(inp, config, rec, answer, crash_after, graph=None):
    graph = graph or _graph()
    latest = {**config, "configurable": {k: v for k, v in config["configurable"].items() if k != "checkpoint_id"}}
    human_inputs = 0
    try:
        state, killed = stream(graph, inp, config, rec, crash_after, rec.prev or None)
        if killed:
            rec.event("killed", recursion_limit=RECURSION_LIMIT)
            say("guard", {"action": "killed", "say": f"LangGraph recursion limit ({RECURSION_LIMIT}) hit. "
                                                      "The agents never decided."})
            summary(state, human_inputs, ended="[red]Killed by the framework. Nobody decided.[/]")
            rec.close(console, state, ended="Killed by the framework. Nobody decided.")
            return state, rec.dir

        # Guardrail 3: the graph paused at interrupt() and is waiting for a human.
        snap = graph.get_state(latest)
        while snap.next and snap.tasks and snap.tasks[0].interrupts:
            proposal = snap.tasks[0].interrupts[0].value
            console.print()
            console.print(f"[bold white]{'You':>9}[/] [bold]APPROVAL[/]     Buy {proposal['quantity']} × {proposal['item']} "
                          f"for ₹{proposal['price']} from {proposal['store']}? (proposed by {proposal['proposed_by']} agent)")
            reply = answer or Prompt.ask(f"{'':>9} Approve or deny", choices=["approve", "deny"],
                                         default="approve", console=console)
            human_inputs += 1
            rec.event("resume", answer=reply, auto=answer is not None)
            state, _ = stream(graph, Command(resume=reply), latest, rec, None, state)
            snap = graph.get_state(latest)
    except BaseException as e:   # Ctrl+C or a crash: keep whatever was logged so far
        rec.event("error", type=type(e).__name__, message=str(e))
        rec.close(console, rec.prev, ended=f"{type(e).__name__}: {e}")
        raise
    summary(state, human_inputs)
    rec.close(console, state)
    return state, rec.dir


def stream(graph, inp, config, rec, crash_after=None, state=None):
    """Run the graph, keeping the latest state. Returns (state, killed_by_recursion_limit).

    "updates" says which node(s) just ran; the "values" chunk after it is the full state, which rec.state() diffs.
    durability="sync" saves each checkpoint before the next step starts, so a crash never loses a finished step.
    """
    names = ["input" if state is None else "resume"]
    try:
        for mode, chunk in graph.stream(inp, config, stream_mode=["updates", "values"], durability="sync"):
            if mode == "updates":
                for name, update in chunk.items():
                    if name == "__interrupt__":
                        names.append("interrupt")
                        rec.event("interrupt", proposal=[i.value for i in update])
                    else:
                        names.append(name)
                        rec.event("node", node=name, update=update)
            else:
                # Parallel nodes (the scouts) each send an update, then one state for the whole step.
                state = {k: v for k, v in chunk.items() if k != "__interrupt__"}
                rec.state(" + ".join(names), state)
                if crash_after and crash_after in names:
                    _crash(rec, crash_after, state)
                names = []
        return state, False
    except GraphRecursionError:
        return state, True


def _crash(rec, node, state):
    say("guard", {"action": "crash", "say": f"Process killed right after '{node}' (simulated). "
                                             "Run: python run.py --resume"})
    rec.event("crash", after=node)
    rec.close(console, state, ended=f"Crashed after {node} (simulated)")
    os._exit(1)   # a hard kill: no cleanup, no goodbye. The checkpoint is already on disk.
