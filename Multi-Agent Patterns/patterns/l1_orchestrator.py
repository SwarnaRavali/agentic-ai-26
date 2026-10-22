"""Level 1 · Orchestrator → workers. You give the goal, not the steps.

    query → planner ⇄ worker (one task at a time, every result back through the planner) → checkout

Communication: hub and spoke. The planner (an LLM) reads the query, chooses the checks and briefs one
worker per check. Workers never talk to each other and pass on only what their brief asked for.
It catches the type and the size ("running" and "size 9"), which the script missed. But no worker's brief is about the seller,
so the cheapest "Sparx" left is a ₹699 one from an unverified reseller.
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from patterns import common as c
from patterns import world

TITLE = "Level 1 · Orchestrator → workers"
HUMAN_STEPS = 1   # one sentence

SKILLS = {
    "search": "find listings by type and colour in every store",
    "size": "keep listings with the user's size in stock",
    "price": "keep listings under the budget",
    "pick": "choose the cheapest remaining listing",
}
PLAN = list(SKILLS)
LABEL = {"search": "Search", "size": "Size", "price": "Price", "pick": "Pick"}


class State(TypedDict, total=False):
    query: str
    plan: list
    next: int
    ids: list      # the listings still in the running, handed from worker to worker through the planner
    pick: str
    answer: str


def planner(state):
    if "plan" in state:
        return {}
    c.step("The planner writes its own plan from the query")
    reply = c.think("planner", f"You are a planner agent. Turn the user's query into checks, in order, using only these "
                               f"workers: {SKILLS}. Start with search and end with pick.",
                    {"query": state["query"]}, ["plan"],
                    offline={"action": "plan", "say": f"Search {world.item_text()}, then {world.size_text()}, then under "
                                                      f"₹{world.GOAL['max_price']:,}, then the cheapest.",
                             "tasks": [s for s in PLAN if s != "size" or world.GOAL.get("size")]},
                    fields={"tasks": f"ordered list of workers from {PLAN}"})
    plan = [s for s in dict.fromkeys(reply.get("tasks") or []) if s in SKILLS and s not in ("search", "pick")]
    plan = ["search", *plan, "pick"]
    c.say("planner", reply["say"])
    c.status("planner", "active", f"plan: {len(plan)} tasks")
    c.note("Hub and spoke: every result goes back through the planner. Workers never talk to each other.", "warn")
    return {"plan": plan, "next": 0}


def route(state):
    return "worker" if state["next"] < len(state["plan"]) else "checkout"


def worker(state):
    skill, g = state["plan"][state["next"]], world.GOAL
    ids = state.get("ids", [])
    c.msg("planner", skill, "task", SKILLS[skill])
    c.status(skill, "active", "working")
    out = {"next": state["next"] + 1}

    if skill == "search":
        ids = [i for s in world.STORES for i in world.search_store(s, g["type"], g["color"])]
        c.tool(skill, "search_store", {"type": g["type"], "color": g["color"]}, f"{len(ids)} listings")
        c.listing(ids, "checked")
        summary = f"{len(ids)} {world.item_text()}"
    elif skill == "size":
        keep = [i for i in ids if world.in_stock(i, g["size"])]
        if g["size"]:
            c.tool(skill, "in_stock", {"size": g["size"]}, f"{len(keep)} have size {g['size']}")
            c.listing([i for i in ids if i not in keep], "out", f"no size {g['size']}")
        ids, summary = keep, f"{len(keep)} in size {g['size']}" if g["size"] else "size not on the page: unverified"
    elif skill == "price":
        keep = [i for i in ids if world.price(i) <= g["max_price"]]
        c.listing([i for i in ids if i not in keep], "out", "over budget")
        ids, summary = keep, f"{len(keep)} under ₹{g['max_price']:,}"
    elif skill != "pick":                    # a skill added to SKILLS needs its own branch above
        raise NotImplementedError(f"worker() has no branch for the {skill!r} skill")
    elif not ids:
        out.update(pick=None, answer="Nothing found.")
        summary = "nothing left to pick"
    else:   # pick: sees only what the earlier workers passed on, name and price
        c.listing(ids, "kept")
        options = [{"id": i, "name": world.name(i), "price": world.price(i)} for i in ids]
        cheapest = min(ids, key=world.price)
        reply = c.think(skill, "You are the pick worker. Choose the cheapest listing from the options.",
                        {"query": state["query"], "options": options}, ids,
                        offline={"action": cheapest, "say": f"Cheapest: {world.name(cheapest)} at ₹{world.price(cheapest):,}."})
        c.say(skill, reply["say"])
        c.listing(reply["action"], "pick")
        out.update(pick=reply["action"], answer=reply["say"])
        summary = world.name(reply["action"])

    c.status(skill, "done", summary)
    c.msg(skill, "planner", "data", summary)
    return {**out, "ids": ids}


def checkout(state):
    if not state.get("pick") or state["pick"] not in world.LISTINGS:
        c.status("checkout", "bad", "nothing to buy")
        return {}
    c.msg("planner", "checkout", "task", f"buy {world.name(state['pick'])}")
    c.status("checkout", "done", "ordered")
    c.listing(state["pick"], "bought")
    c.say("checkout", f"Simulated order: 1 × {world.label(state['pick'])}")
    seller = world.LISTINGS[state["pick"]]["seller"]
    if not world.SELLERS[seller]["verified"]:
        c.note(f"Sold by “{seller}”, an unverified reseller. No worker’s brief was about the seller.", "bad")
    return {}


def build():
    g = StateGraph(State)
    g.add_node("planner", planner)
    g.add_node("worker", worker)
    g.add_node("checkout", checkout)
    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", route, ["worker", "checkout"])
    g.add_edge("worker", "planner")          # hub and spoke: every result returns to the planner
    g.add_edge("checkout", END)
    return g.compile()


def run():
    c.agent("planner", "Planner")
    for s in SKILLS:
        c.agent(s, LABEL.get(s, s.title()))
    c.step("You give one sentence: the query")
    c.msg("you", "planner", "task", world.QUERY)
    return build().invoke({"query": world.QUERY})
