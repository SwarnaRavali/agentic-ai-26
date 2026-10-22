"""The agent team: one graph, every pattern in the lab.

  price drop → watcher → scout × N (parallel, one per store) → evaluator → deal ⇄ budget → checkout
                                                                              ↘ escalate

Patterns: event-driven start (watcher), specialists in parallel (Send = fan out, one edge = fan in),
one owner per task, budget and stop, human approval, and a checkpointer that makes the run durable.
The guardrails live in lab/guards.py and are switched by the run's config.
"""
import time

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from lab import feed, guards, llm
from lab.core import State, note, say, watcher_node

ROLE = {
    "deal": "You are the Deal agent. You are responsible for buying good deals quickly.",
    "budget": "You are the Budget agent. You are responsible for all purchases.",
}


def check_store(store):
    """The scouts' tool: look up the matching item in one store."""
    return next(i for i in feed.read_feed() if i["store"] == store)


def fan_out(state: State):
    # One scout per store in the feed. Add a store to feed.DEFAULT_ITEMS and you get another scout.
    return [Send("scout", {"store": i["store"]}) for i in feed.read_feed()]


def scout(inp: dict):
    store = inp["store"]
    start = time.time()
    item = check_store(store)
    reply, tok = llm.ask("scout", f"You are a Scout agent. You check {store} only and report its offer.",
                         {"store": store, "item": item, "goal": feed.GOAL}, ["offer", "no_offer"])
    say("scout", reply, tok)
    # Parallel nodes can only append to lists; the evaluator adds up their turns and tokens.
    return {"offers": [{**item, "action": reply["action"], "tokens": tok, "start": start, "end": time.time()}],
            "log": [{"from": f"scout:{store}", **reply}]}


def evaluator(state: State):
    offers = state["offers"]
    wall = max(o["end"] for o in offers) - min(o["start"] for o in offers)
    note(f"{len(offers)} scouts ran in parallel: {wall:.1f}s, instead of "
         f"{sum(o['end'] - o['start'] for o in offers):.1f}s one after another.", "green")
    seen = [{k: o[k] for k in ("store", "name", "price", "action")} for o in offers]
    reply, tok = llm.ask("evaluator", "You are an Evaluator agent. Pick the best offer that meets the saved goal.",
                         {"event": state["event"], "offers": seen}, ["recommend", "reject"])
    say("evaluator", reply, tok)
    best = min((o for o in offers if o["price"] <= feed.GOAL["max_price"]), key=lambda o: o["price"], default=None)
    return {"tokens": state.get("tokens", 0) + tok + sum(o["tokens"] for o in offers),
            "best": best and {**best, "goal": feed.GOAL}, "log": [{"from": "evaluator", **reply}]}


def make_buyer(name):
    """Deal and Budget were both told purchases are their job. Only the guardrails keep them from both buying."""
    def agent(state: State, config):
        owner_rule = guards.enabled(config, "owner")
        chaos = config["configurable"].get("chaos", False)
        ctx = {"event": state["best"], "other_last": state.get("last"), "turn": state.get("turn", 0),
               "owner": state.get("owner"), "owner_rule": owner_rule, "chaos": chaos,
               "i_added": any(c["by"] == name for c in state.get("cart", []))}
        actions = ["claim", "stand_down", "buy", "recheck"] if owner_rule else ["claim", "dispute", "add_to_cart"]
        reply, tok = llm.ask(name, ROLE[name], ctx, actions)
        update = {"turn": state.get("turn", 0) + 1, "tokens": state.get("tokens", 0) + tok}
        if owner_rule and reply["action"] in ("claim", "buy"):
            owner = guards.claim(state, name)
            if owner is None:
                reply = {"action": "stand_down", "say": f"Rejected by code: {state['owner']} agent owns this task."}
            else:
                update["owner"] = owner
        say(name, reply, tok)
        if reply["action"] == "add_to_cart":
            update["cart"] = [{"sku": state["best"]["sku"], "by": name}]
            note(f"cart now has {len(state.get('cart', [])) + 1} item(s)", "red")
        update.update(last={"from": name, **reply}, log=[{"from": name, **reply}])
        return update
    return agent


def checkout(state: State, config):
    item = state["best"]
    proposal = {"item": item["name"], "price": item["price"], "store": item["store"],
                "quantity": 1, "proposed_by": state["owner"]}
    if guards.enabled(config, "approval"):
        if not guards.approve(proposal):
            say("checkout", {"action": "cancelled", "say": "Human said no. Nothing ordered."})
            return {"outcome": "Cancelled by a human."}
        outcome = "Bought 1 item, approved by a human."
    else:
        outcome = "Bought 1 item. Nobody approved it."
    say("checkout", {"action": "ordered", "say": f"Simulated order: 1 × {item['name']} at ₹{item['price']} from {item['store']}."})
    if not guards.enabled(config, "approval"):
        note("No human was asked before buying.", "yellow")
    return {"cart": [{"sku": item["sku"], "by": state["owner"]}], "outcome": outcome}


def escalate(state: State):
    say("guard", {"action": "stopped", "say": f"Budget hit: {state['turn']} turns, ~{state['tokens']:,} tokens. "
                                               "Stopping and asking a human."})
    return {"outcome": "Stopped by budget. Escalated to a human."}


def after_evaluator(state: State):
    return "deal" if state.get("best") else END


def route(state: State, config):
    if guards.enabled(config, "budget") and not guards.within_budget(state):
        return "escalate"
    last = state["last"]
    if guards.enabled(config, "owner"):
        if last["action"] == "buy":
            return "checkout"
        if last["action"] == "stand_down":
            return state["owner"]
        if last["action"] == "recheck":
            return last["from"]
    # Whoever spoke last, the other one replies. Without the owner rule nothing ever ends the loop.
    return "budget" if last["from"] == "deal" else "deal"


def build(checkpointer=None):
    g = StateGraph(State)
    g.add_node("watcher", watcher_node)
    g.add_node("scout", scout)
    g.add_node("evaluator", evaluator)
    g.add_node("deal", make_buyer("deal"))
    g.add_node("budget", make_buyer("budget"))
    g.add_node("checkout", checkout)
    g.add_node("escalate", escalate)
    g.add_edge(START, "watcher")
    g.add_conditional_edges("watcher", fan_out, ["scout"])   # fan out: every scout at once
    g.add_edge("scout", "evaluator")                         # fan in: waits for all of them
    g.add_conditional_edges("evaluator", after_evaluator, ["deal", END])
    g.add_conditional_edges("deal", route, ["deal", "budget", "checkout", "escalate"])
    g.add_conditional_edges("budget", route, ["deal", "budget", "checkout", "escalate"])
    g.add_edge("checkout", END)
    g.add_edge("escalate", END)
    return g.compile(checkpointer=checkpointer)
