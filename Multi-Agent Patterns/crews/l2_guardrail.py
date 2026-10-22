"""Level 2 in CrewAI · async scouts, and the critic as a task guardrail.

    scout task × 3 stores (async_execution=True, in parallel) → evaluator task (guardrail=critic)
                                                                   ↺ guardrail fails: retry with the feedback

Differences from LangGraph:
  - fan out is a task flag (async_execution=True); fan in is the next task's context. No Send(), no reducers.
  - the rework loop is built in: a guardrail returns (False, "why") and CrewAI re-runs the same agent with
    that feedback, up to guardrail_max_retries. In LangGraph the loop is two conditional edges you draw.
  - the critic here is a plain function. A guardrail can also be a sentence, checked by an LLM.
"""
from crewai import Crew, Process

from crews import kit
from crews.contracts import Choice, Shortlist
from patterns import common as c
from patterns import world

TITLE = "Level 2 · Async tasks + guardrail"
HUMAN_STEPS = 1


def matches(store):
    return [i for i in world.search_store(store) if world.fits(i)]


def key(store):
    return "listings_" + store[-1]


def build(ask_first=False):
    rejected = []

    def scout_done(store):
        def cb(output):
            me, ok = "scout-" + store, kit.value(output, Shortlist).listing_ids
            ids = world.search_store(store)
            c.listing(ids, "checked")
            c.listing([i for i in ids if i not in ok], "out")
            c.listing(ok, "kept")
            c.status(me, "done", f"{len(ok)} match" if ok else "no match")
            c.msg(me, "evaluator", "data", kit.value(output, Shortlist).note)
        return cb

    def critic(output):
        """The guardrail. Clean context: it sees only the pick, and checks the seller register."""
        pick = kit.value(output, Choice).listing_id
        if pick not in world.LISTINGS:                 # nothing to check: nothing will be bought
            return True, output
        c.listing(pick, "pick")
        c.status("evaluator", "done", world.name(pick))
        c.msg("evaluator", "critic", "data", f"pick: {world.label(pick)}")
        c.status("critic", "active", "checking seller")
        s = world.seller_check(pick)
        c.tool("critic", "seller_check", {"listing": world.name(pick)}, f"{s['seller']}: {s['note']}")
        if not s["verified"]:
            rejected.append(pick)
            c.listing(pick, "rejected", s["note"])
            c.status("critic", "bad", "rejected")
            c.msg("critic", "evaluator", "flag", f"{s['seller']} is not a verified seller. Pick again.", tone="bad")
            c.note("The guardrail failed, so CrewAI re-runs the evaluator with the critic's feedback.", "bad")
            return False, (f"Listing {pick} is sold by {s['seller']}, which is not a verified seller ({s['note']}). "
                           "Choose a different listing.")
        c.status("critic", "done", "approved")
        c.msg("critic", "checkout", "ok", "Verified seller. Approved.")
        return True, output

    scouts, tasks = [], []
    for s in world.STORES:
        a = kit.agent("scout-" + s, "Scout for " + s, "Report which of this store's listings match the query.",
                      Shortlist, lambda s=s: Shortlist(listing_ids=matches(s), note=(
                          f"{len(matches(s))} match: " + ", ".join(f"{world.name(i)} ₹{world.price(i):,}" for i in matches(s))
                          if matches(s) else "Nothing here matches.")))
        scouts.append(a)
        tasks.append(kit.task("Query: {query}\nListings in " + s + ": {" + key(s) + "}\nReturn the IDs that match "
                              "every requirement in the query.", a, Shortlist, callback=scout_done(s),
                              async_execution=True))

    def best():
        left = [i for s in world.STORES for i in matches(s) if i not in rejected]
        return Choice(listing_id=kit.cheapest(left), reason=f"Best offer: {world.label(kit.cheapest(left))}.")

    evaluator = kit.agent("evaluator", "Evaluator", "Pick the cheapest listing that meets the query.", Choice, best)
    tasks.append(kit.task("Query: {query}\nListings: {listings}\nFrom the scouts' matches, pick the cheapest listing.",
                          evaluator, Choice,
                          context=list(tasks), guardrail=critic, guardrail_max_retries=2))
    return Crew(agents=scouts + [evaluator], tasks=tasks, process=Process.sequential, verbose=False)


def team(lead_label):
    c.agent("lead", lead_label)
    for s in world.STORES:
        c.agent("scout-" + s, "Scout")
    c.agent("evaluator", "Evaluator")
    c.agent("critic", "Guardrail", role="critic")


def run_team(ask_first=False):
    c.step("Three async tasks start at once, one per store")
    c.status("lead", "done", f"{len(world.STORES)} async tasks")
    for s in world.STORES:
        c.msg("lead", "scout-" + s, "task", f"check {s}")
        c.status("scout-" + s, "active", "searching")
    inputs = {"query": world.QUERY, "listings": kit.listings(),   # the evaluator compares prices, not the scouts' notes
              **{key(s): kit.listings(world.search_store(s)) for s in world.STORES}}
    result = build(ask_first).kickoff(inputs=inputs)
    pick = kit.bought(kit.value(result, Choice).listing_id)
    if pick is None:
        c.status("checkout", "bad", "nothing to buy")
        return {"pick": None, "answer": "Nothing found."}
    if ask_first:
        c.status("checkout", "waiting", "asks you")
        c.emit("notify", title=f"{world.name(pick)} · ₹{world.price(pick):,}", text=world.proposal(pick))
    else:
        c.status("checkout", "done", "ordered")
        c.listing(pick, "bought")
        c.say("checkout", f"Simulated order: 1 × {world.label(pick)}")
    return {"pick": pick, "answer": kit.value(result, Choice).reason}


def run():
    team("Crew")
    c.step("You give one sentence: the query")
    c.msg("you", "lead", "task", world.QUERY)
    return run_team()
