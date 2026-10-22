"""Level 1 in CrewAI · a planner task, then worker tasks that get the plan as context.

    plan task → search task → size task → price task → pick task      (Process.sequential, plan in every context)

Difference from LangGraph: in LangGraph the planner chose the workers at run time. A Crew's task list is fixed
when the crew is built, so here the developer wrote the workers and the plan can only shape what they do.
Same weakness: no task is about the seller, so the cheapest "Sparx" is a ₹699 fake.
"""
from crewai import Crew, Process

from crews import kit
from crews.contracts import Choice, Plan, Shortlist
from patterns import common as c
from patterns import world

TITLE = "Level 1 · Planner + fixed tasks"
HUMAN_STEPS = 1
G = world.GOAL


def build():
    found = lambda: [i for s in world.STORES for i in world.search_store(s, G["type"], G["color"])]   # noqa: E731
    sized = lambda: [i for i in found() if world.in_stock(i, G["size"])]                             # noqa: E731
    cheap = lambda: [i for i in sized() if world.price(i) <= G["max_price"]]                          # noqa: E731
    checks = [world.item_text(), world.size_text(), f"under ₹{G['max_price']:,}", "the cheapest"]
    planner = kit.agent("planner", "Planner", "Turn the user's query into checks for the workers.", Plan,
                        lambda: Plan(checks=checks, note=f"Search {world.item_text()}, then {world.size_text()}, then under "
                                                          f"₹{G['max_price']:,}, then the cheapest."))
    workers = {
        "search": (kit.agent("search", "Search", "Find listings of the right type and colour.", Shortlist,
                             lambda: Shortlist(listing_ids=found(), note=f"{len(found())} {world.item_text()}")),
                   "Return the IDs of listings matching the type and colour in the plan."),
        "size": (kit.agent("size", "Size", "Keep listings with the user's size in stock.", Shortlist,
                           lambda: Shortlist(listing_ids=sized(), note=f"{len(sized())} in size {G['size']}" if G["size"]
                                             else "size not on the page: unverified")),
                 "From the previous IDs, keep those with the size in the plan in stock."),
        "price": (kit.agent("price", "Price", "Keep listings under the budget.", Shortlist,
                            lambda: Shortlist(listing_ids=cheap(), note=f"{len(cheap())} under ₹{G['max_price']:,}")),
                  "From the previous IDs, keep those under the budget in the plan."),
        "pick": (kit.agent("pick", "Pick", "Choose the cheapest remaining listing.", Choice,
                           lambda: Choice(listing_id=kit.cheapest(cheap()), reason="Cheapest listing left.")),
                 "From the previous IDs, choose the cheapest."),
    }
    order, seen = list(workers), {"ids": []}

    def planned(output):
        v = kit.value(output, Plan)
        c.say("planner", v.note)
        c.status("planner", "active", f"plan: {len(v.checks)} checks")
        c.note("The plan is context for every task. The tasks themselves were fixed when the crew was built.", "warn")
        c.msg("planner", "search", "task", workers["search"][1])

    def finished(me):
        def cb(output):
            nxt = order[order.index(me) + 1] if me != "pick" else None
            if me == "pick":
                v = kit.value(output, Choice)
                c.listing(seen["ids"], "kept")
                c.listing(v.listing_id, "pick")
                c.say("pick", v.reason)
                c.status("pick", "done", world.name(v.listing_id))
                c.msg("pick", "planner", "data", world.name(v.listing_id))
                return
            v = kit.value(output, Shortlist)
            if me == "search":
                c.listing(v.listing_ids, "checked")
            else:
                c.listing([i for i in seen["ids"] if i not in v.listing_ids], "out",
                          f"no size {G['size']}" if me == "size" else "over budget")
            seen["ids"] = v.listing_ids
            c.status(me, "done", v.note)
            c.msg(me, "planner", "data", v.note)
            c.msg("planner", nxt, "task", workers[nxt][1])
        return cb

    plan = kit.task("Query: {query}\nTurn it into checks, in order, for these workers: search by type and colour, "
                    "size in stock, price under the budget, pick the cheapest.", planner, Plan, callback=planned)
    tasks, prev = [plan], None
    for name, (agent, text) in workers.items():
        model = Choice if name == "pick" else Shortlist
        t = kit.task("Listings: {listings}\n" + text, agent, model, context=[plan] + ([prev] if prev else []),
                     callback=finished(name))
        tasks.append(t)
        prev = t
    return Crew(agents=[planner] + [a for a, _ in workers.values()], tasks=tasks, process=Process.sequential,
                verbose=False)


def run():
    c.agent("planner", "Planner")
    for s in ("search", "size", "price", "pick"):
        c.agent(s, s.title())
    c.step("You give one sentence: the query")
    c.msg("you", "planner", "task", world.QUERY)
    result = build().kickoff(inputs={"query": world.QUERY, "listings": kit.listings()})
    pick = kit.bought(kit.value(result, Choice).listing_id)
    if pick is None:
        c.status("checkout", "bad", "nothing to buy")
        return {"pick": None, "answer": "Nothing found."}
    c.msg("planner", "checkout", "task", f"buy {world.name(pick)}")
    c.status("checkout", "done", "ordered")
    c.listing(pick, "bought")
    c.say("checkout", f"Simulated order: 1 × {world.label(pick)}")
    seller = world.LISTINGS[pick]["seller"]
    if not world.SELLERS[seller]["verified"]:
        c.note(f"Sold by “{seller}”, an unverified reseller. No task was about the seller.", "bad")
    return {"pick": pick, "answer": kit.value(result, Choice).reason}
