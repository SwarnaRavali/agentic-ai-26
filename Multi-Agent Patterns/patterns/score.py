"""Grade a purchase against the query, the same way for every level and both frameworks.

Demo stores, four checks:            Live sites, four checks (a search page can't show size):
  black running shoe   type, colour     black running shoe   "black" and "running" in the evidence
  size 9 in stock      the user's size  under ₹1,000         the observed price
  under ₹1,000         the price paid   verified evidence    the store's own site, product page read,
  genuine seller       not a reseller                        not a search-index fallback, fresh
                                        cheapest match       no cheaper listing passes the other three
In the demo stores the cheapest-match check isn't needed: the traps are built into the data.
The names come from the goal: another query gets its own ("grey running shoe", no size check if it names none).
"""
from patterns import world


def names():
    """The checks for the current goal, in order."""
    g, demo = world.GOAL, world.SOURCE.get("kind") == "demo"
    return ([world.item_text(plural=False)] + ([f"size {g['size']} in stock"] if g.get("size") else [])
            + [f"under ₹{g['max_price']:,}", "genuine seller" if demo else "verified evidence"]
            + ([] if demo else ["cheapest match"]))


def _kind(x, g):
    return (g.get("type") is None or x["type"] == g["type"]) and (g.get("color") is None or x["color"] == g["color"])


def checks(lid):
    x, g = world.LISTINGS[lid], world.GOAL
    seller = world.SELLERS[x["seller"]]
    words = [(k, g[k]) for k in ("color", "type") if g.get(k)]
    c = {world.item_text(plural=False): (_kind(x, g), f"{x['color']} {x['type']}" if world.SOURCE["kind"] == "demo"
                                         else (" and ".join(f"“{w}”" for _, w in words) + " in the evidence" if _kind(x, g)
                                               else "evidence says: " + ", ".join(w if x[k] == w else f"not {w}"
                                                                                  for k, w in words)))}
    if g.get("size"):
        c[f"size {g['size']} in stock"] = (g["size"] in (x["sizes"] or []),
                                           "sizes " + ", ".join(map(str, x["sizes"])) if x["sizes"] else "size unverified")
    c[f"under ₹{g['max_price']:,}"] = (world.price(lid) <= g["max_price"], f"₹{world.price(lid):,}")
    who = "genuine seller" if world.SOURCE["kind"] == "demo" else "verified evidence"
    c[who] = (seller["verified"], f"{x['seller']}: {seller['note']}" if world.SOURCE["kind"] == "demo" else seller["note"])
    if world.SOURCE["kind"] != "demo":
        ok = [i for i in world.LISTINGS if _passes(i)]
        best = min((world.price(i) for i in ok), default=None)
        c["cheapest match"] = (best is not None and lid in ok and world.price(lid) == best,
                               f"cheapest match is ₹{best:,}" if best is not None else "nothing passes")
    return c


def _passes(lid):
    x, g = world.LISTINGS[lid], world.GOAL
    return _kind(x, g) and world.price(lid) <= g["max_price"] and world.SELLERS[x["seller"]]["verified"]


def grade(lid):
    """None if nothing was bought, or the pick isn't a listing in this world (a model can invent an id)."""
    if lid not in world.LISTINGS:
        return None
    x, c = world.LISTINGS[lid], checks(lid)
    ok = {k: v[0] for k, v in c.items()}
    return {"pick": lid, "name": x["name"], "store": x["store"], "price": world.price(lid), "url": x.get("url"),
            "checks": ok, "why": {k: v[1] for k, v in c.items()}, "score": sum(ok.values()), "of": len(ok)}
