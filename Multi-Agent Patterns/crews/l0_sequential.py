"""Level 0 in CrewAI · a sequential crew. A developer wrote three tasks; Process.sequential runs them in order.

    search task → filter task → pick task        (each task's output is the next one's context)

Same weakness as the LangGraph pipeline: the developer turned the query into one search keyword (its colour)
and a price cap. The tasks never mention the type or the size, and the agents never see the query, so those
requirements disappear (for the default query: "running" and "size 9"). Difference: in CrewAI each step is an LLM agent
reading the previous output, not code, so even a fixed pipeline spends a model call per step.
"""
from crewai import Crew, Process

from crews import kit
from crews.contracts import Choice, Shortlist
from patterns import common as c
from patterns import world

TITLE = "Level 0 · Sequential crew"
HUMAN_STEPS = 4


def build():
    word, budget = world.keyword(), world.GOAL["max_price"]   # all the developer took from the query
    found = lambda: world.search_catalog(word)                                         # noqa: E731
    cheap = lambda: [i for i in found() if world.price(i) <= budget]                   # noqa: E731
    search = kit.agent("search", "Search", f"List listings whose name contains '{word}'.", Shortlist,
                       lambda: Shortlist(listing_ids=found(), note=f"{len(found())} listings with “{word}”"))
    filt = kit.agent("filter", "Filter", f"Keep listings priced at or under ₹{budget:,}.", Shortlist,
                     lambda: Shortlist(listing_ids=cheap(), note=f"{len(cheap())} under ₹{budget:,}"))
    pick = kit.agent("pick", "Pick", "Choose the cheapest listing.", Choice,
                     lambda: Choice(listing_id=kit.cheapest(cheap()), reason="Cheapest listing left."))

    def done(me, nxt, state, model):
        def cb(output):
            v = kit.value(output, model)
            if model is Shortlist:
                c.listing(v.listing_ids, state)
                c.status(me, "done", v.note)
                c.msg(me, nxt, "data", v.note)
            else:
                c.listing(v.listing_id, "pick", v.reason)
                c.status(me, "done", world.name(v.listing_id))
                c.msg(me, nxt, "task", f"buy {world.name(v.listing_id)}")
        return cb

    t1 = kit.task(f"Listings: {{listings}}\nReturn the IDs of listings whose name contains '{word}'.", search, Shortlist,
                  callback=done("search", "filter", "checked", Shortlist))
    t2 = kit.task(f"Listings: {{listings}}\nKeep only the IDs from the previous step priced at or under ₹{budget:,}.",
                  filt, Shortlist, context=[t1], callback=done("filter", "pick", "kept", Shortlist))
    t3 = kit.task("Listings: {listings}\nReturn the cheapest of the IDs from the previous step.", pick, Choice,
                  context=[t2], callback=done("pick", "checkout", "pick", Choice))
    return Crew(agents=[search, filt, pick], tasks=[t1, t2, t3], process=Process.sequential, verbose=False)


def run():
    for id, label in (("search", "Search"), ("filter", "Filter"), ("pick", "Pick")):
        c.agent(id, label)
    c.step("A developer wrote three tasks; Process.sequential runs them in order")
    c.msg("you", "search", "task", world.QUERY)
    result = build().kickoff(inputs={"listings": kit.listings()})
    pick = kit.bought(kit.value(result, Choice).listing_id)
    if pick is None:
        c.status("checkout", "bad", "nothing to buy")
        return {"pick": None, "answer": "Nothing found."}
    c.status("checkout", "done", "ordered")
    c.listing(pick, "bought")
    c.say("checkout", f"Simulated order: 1 × {world.label(pick)}")
    c.note(f"No task mentions {world.dropped_text()}, and no agent sees the query. The requirement disappears.", "bad")
    return {"pick": pick, "answer": kit.value(result, Choice).reason}
