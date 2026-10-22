"""Shared pieces: the graph state, the watcher node, and terminal output."""
import operator
import os
import time
from typing import Annotated, Optional, TypedDict

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from lab import llm

console = Console(highlight=False, record=True)   # record: saved to output/<run>/console.log
DELAY = float(os.getenv("LAB_DELAY", "0.7"))  # pause between lines so the room can read


class State(TypedDict, total=False):
    event: dict                                # what happened in the world
    log: Annotated[list, operator.add]         # every agent message
    cart: Annotated[list, operator.add]        # items added to cart
    offers: Annotated[list, operator.add]      # one offer per scout
    best: Optional[dict]                       # the evaluator's pick
    owner: Optional[str]                       # guardrail 1: who owns the purchase
    last: dict                                 # last message, used for routing
    turn: int                                  # buyer turns so far
    tokens: int                                # tokens used so far
    outcome: str                               # how the run ended


COLORS = {"watcher": "magenta", "scout": "orange1", "evaluator": "cyan", "deal": "dodger_blue1",
          "budget": "yellow", "checkout": "green", "guard": "red", "human": "bold white"}


def say(agent, reply, tokens=None):
    color = COLORS.get(agent, "white")
    action = reply.get("action", "").upper()
    tok = f" [dim]· {tokens} tok[/]" if tokens else ""
    console.print(f"[{color}]{agent.title():>9}[/] [bold]{action:<12}[/] {reply.get('say', '')}{tok}")
    time.sleep(DELAY)


def note(text, style="dim"):
    console.print(f"[{style}]{'':>9} {text}[/]")
    time.sleep(DELAY * 0.6)


def header(label, title, subtitle):
    console.print()
    console.print(Panel(f"[bold]{title}[/]\n[dim]{subtitle}[/]", title=label, title_align="left",
                        border_style="cyan", padding=(0, 1)))


def watcher_node(state: State):
    """First node. The graph was started by an event, not by a person."""
    reply, tok = llm.ask("watcher", "You are a Watcher agent. Decide if this event matches the saved goal.",
                         {"event": state["event"]}, ["trigger", "ignore"])
    say("watcher", reply, tok)
    return {"tokens": state.get("tokens", 0) + tok, "log": [{"from": "watcher", **reply}]}


def summary(state, human_inputs=0, ended=None):
    cart = state.get("cart", [])
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_row("Human inputs", f"[bold]{human_inputs}[/]")
    t.add_row("Agent turns", str(state.get("turn", 0)))
    t.add_row("Messages", str(len(state.get("log", []))))
    t.add_row("Tokens (est.)", f"{state.get('tokens', 0):,}")
    t.add_row("Items in cart", f"[{'red' if len(cart) > 1 else 'green'}]{len(cart)}[/]")
    t.add_row("Outcome", ended or state.get("outcome", "—"))
    console.print(Panel(t, title="Run summary", title_align="left", border_style="dim"))
