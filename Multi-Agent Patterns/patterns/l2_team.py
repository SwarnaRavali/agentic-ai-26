"""Level 2 · A team with a critic. Specialists in parallel, a reviewer that can say no.

    query → coordinator ─Send→ scout × 3 stores (in parallel) ─→ evaluator ⇄ critic ─→ checkout

Communication patterns:
  fan out / fan in   one scout per store, all at once; the evaluator waits for every one of them
  critic             a reviewer with a clean context: it sees only the pick and checks the seller
  rework loop        a rejected pick goes back to the evaluator, which picks again

The critic is what fixes the answer: it rejects the ₹699 "Sparx" from an unverified reseller that
Level 1 bought.
"""
import operator
from typing import Annotated, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from patterns import common as c
from patterns import world

TITLE = "Level 2 · Team + critic"
HUMAN_STEPS = 1


class State(TypedDict, total=False):
    query: str
    ask_first: bool                          # Level 3: propose to the user instead of ordering
    offers: Annotated[list, operator.add]    # parallel scouts can only append
    rejected: Annotated[list, operator.add]
    pick: Optional[str]
    answer: str


def lead(state):
    c.step("One scout per store, all at once")
    c.status("lead", "done", f"{len(world.STORES)} scouts")
    return {}


def fan_out(state):
    return [Send("scout", {"store": s, "query": state["query"]}) for s in world.STORES]


def scout(inp):
    store = inp["store"]
    me = "scout-" + store
    c.msg("lead", me, "task", f"check {store}")
    c.status(me, "active", "searching")
    ids = world.search_store(store)
    c.listing(ids, "checked")
    ok = [i for i in ids if world.fits(i)]
    c.listing([i for i in ids if i not in ok], "out")
    c.listing(ok, "kept")
    reply = c.think(me, f"You are a scout for {store}. Report which listings match the query.",
                    {"query": inp["query"], "matches": [world.label(i) for i in ok]}, ["offer", "no_offer"],
                    offline={"action": "offer" if ok else "no_offer",
                             "say": f"{len(ok)} match: " + ", ".join(f"{world.name(i)} ₹{world.price(i):,}" for i in ok)
                                    if ok else "Nothing here matches."})
    c.status(me, "done", f"{len(ok)} match" if ok else "no match")
    c.msg(me, "evaluator", "data", reply["say"])
    return {"offers": ok}


def evaluator(state):
    left = [i for i in state["offers"] if i not in state.get("rejected", [])]
    c.status("evaluator", "active", "comparing")
    if not left:
        c.say("evaluator", "No offer is left that meets the query.", "bad")
        return {"pick": None, "answer": "Nothing found."}
    cheapest = min(left, key=world.price)
    reply = c.think("evaluator", "You are the evaluator. Pick the best listing for the query: the cheapest that meets it.",
                    {"query": state["query"], "offers": [{"id": i, "listing": world.label(i)} for i in left]}, left,
                    offline={"action": cheapest, "say": f"Best offer: {world.label(cheapest)}."})
    c.say("evaluator", reply["say"])
    c.listing(reply["action"], "pick")
    c.status("evaluator", "done", world.name(reply["action"]))
    c.msg("evaluator", "critic", "data", f"pick: {world.label(reply['action'])}")
    return {"pick": reply["action"], "answer": reply["say"]}


def critic(state):
    """Clean context: the critic sees the pick and the seller register, not how the team got there."""
    pick = state["pick"]
    c.status("critic", "active", "checking seller")
    s = world.seller_check(pick)
    c.tool("critic", "seller_check", {"listing": world.name(pick)}, f"{s['seller']}: {s['note']}")
    reply = c.think("critic", "You are a critic. Reject the pick if the seller is not verified.",
                    {"pick": world.label(pick), "seller": s}, ["ok", "flag"],
                    offline={"action": "ok" if s["verified"] else "flag",
                             "say": "Verified seller. Approved." if s["verified"]
                                    else f"{s['seller']} is not a verified seller. Pick again."})
    flagged = not s["verified"] or reply["action"] == "flag"   # the rule is code; the model can add caution
    if flagged:
        c.listing(pick, "rejected", s["note"])
        c.status("critic", "bad", "rejected")
        c.msg("critic", "evaluator", "flag", reply["say"], tone="bad")
        c.note("The critic rejected the unverified reseller: the one Level 1 bought.", "bad")
        return {"rejected": [pick]}
    c.status("critic", "done", "approved")
    c.msg("critic", "checkout", "ok", reply["say"])
    return {}


def after_critic(state):
    return "evaluator" if state.get("pick") in state.get("rejected", []) else "checkout"


def after_evaluator(state):
    return "critic" if state.get("pick") else "checkout"


def checkout(state):
    pick = state.get("pick")
    if not pick:
        c.status("checkout", "bad", "nothing to buy")
        return {}
    if state.get("ask_first"):
        c.status("checkout", "waiting", "asks you")
        c.emit("notify", title=f"{world.name(pick)} · ₹{world.price(pick):,}", text=world.proposal(pick))
    else:
        c.status("checkout", "done", "ordered")
        c.listing(pick, "bought")
        c.say("checkout", f"Simulated order: 1 × {world.label(pick)}")
    return {}


def build():
    g = StateGraph(State)
    for n, f in (("lead", lead), ("scout", scout), ("evaluator", evaluator), ("critic", critic), ("checkout", checkout)):
        g.add_node(n, f)
    g.add_edge(START, "lead")
    g.add_conditional_edges("lead", fan_out, ["scout"])                  # fan out: every store at once
    g.add_edge("scout", "evaluator")                                    # fan in: waits for all scouts
    g.add_conditional_edges("evaluator", after_evaluator, ["critic", "checkout"])
    g.add_conditional_edges("critic", after_critic, ["evaluator", "checkout"])   # rework loop
    g.add_edge("checkout", END)
    return g.compile()


def team(lead_label):
    c.agent("lead", lead_label)
    for s in world.STORES:
        c.agent("scout-" + s, "Scout")
    c.agent("evaluator", "Evaluator")
    c.agent("critic", "Critic", role="critic")


def run():
    team("Coordinator")
    c.step("You give one sentence: the query")
    c.msg("you", "lead", "task", world.QUERY)
    return build().invoke({"query": world.QUERY})
