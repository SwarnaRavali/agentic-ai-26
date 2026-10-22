"""Level 0 · Scripted pipeline. A developer decided every step at build time.

    query → search → filter → pick → checkout

Communication: fixed hand-offs, each box passes its output to the next. Nobody can add a step.
The developer searched for one keyword from the query (its colour), filtered on price and picked the cheapest.
Nobody wrote a step for the type or the size ("running" and "size 9" in the default query), so those
requirements are silently dropped. The LLM only writes the confirmation.
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from patterns import common as c
from patterns import world

TITLE = "Level 0 · Scripted pipeline"
HUMAN_STEPS = 4   # the developer wrote 3 steps; the user typed the query


class State(TypedDict, total=False):
    query: str
    found: list
    candidates: list
    pick: str
    answer: str


def search(state):
    c.status("search", "active", "searching")
    word = world.keyword()
    found = world.search_catalog(word)
    c.tool("search", "search_catalog", {"keyword": word}, f"{len(found)} listings")
    c.listing(found, "checked")
    c.status("search", "done", f"{len(found)} found")
    c.msg("search", "filter", "data", f"{len(found)} listings with “{word}”")
    return {"found": found}


def filter_price(state):
    c.status("filter", "active", "filtering")
    ok = [i for i in state["found"] if world.price(i) <= world.GOAL["max_price"]]
    c.listing([i for i in state["found"] if i not in ok], "out", "over budget")
    c.listing(ok, "kept")
    c.status("filter", "done", f"{len(ok)} under ₹{world.GOAL['max_price']:,}")
    c.msg("filter", "pick", "data", f"{len(ok)} under ₹{world.GOAL['max_price']:,}")
    return {"candidates": ok}


def pick(state):
    c.status("pick", "active", "picking")
    if not state["candidates"]:
        c.status("pick", "bad", "nothing left")
        return {"pick": None, "answer": "Nothing found."}
    best = min(state["candidates"], key=world.price)   # the developer's rule: cheapest wins
    c.listing(best, "pick", "cheapest")
    reply = c.think("pick", "You are the last step of a fixed pipeline. The cheapest listing was picked by code. "
                            "Write one sentence confirming the purchase for the user.",
                    {"query": state["query"], "picked": world.label(best)}, ["confirm"],
                    offline={"action": "confirm", "say": f"Cheapest match: {world.label(best)}."})
    c.say("pick", reply["say"])
    c.status("pick", "done", world.name(best))
    c.msg("pick", "checkout", "task", f"buy {world.name(best)}")
    return {"pick": best, "answer": reply["say"]}


def checkout(state):
    if not state.get("pick"):
        c.status("checkout", "bad", "nothing to buy")
        return {}
    c.status("checkout", "done", "ordered")
    c.listing(state["pick"], "bought")
    c.say("checkout", f"Simulated order: 1 × {world.label(state['pick'])}")
    c.note(f"No box in the script checks {world.dropped_text()}. The requirement just disappears.", "bad")
    return {}


def build():
    g = StateGraph(State)
    for n, f in (("search", search), ("filter", filter_price), ("pick", pick), ("checkout", checkout)):
        g.add_node(n, f)
    g.add_edge(START, "search")
    g.add_edge("search", "filter")
    g.add_edge("filter", "pick")
    g.add_edge("pick", "checkout")
    g.add_edge("checkout", END)
    return g.compile()


def run():
    for id, label in (("search", "Search"), ("filter", "Filter"), ("pick", "Pick")):
        c.agent(id, label)
    c.step("A developer wired four boxes: search → filter → pick → checkout")
    c.msg("you", "search", "task", world.QUERY)
    return build().invoke({"query": world.QUERY})
