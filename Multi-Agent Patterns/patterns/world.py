"""The agents' world: stores, their listings, a seller register and a price feed.

Two kinds of world, same shape, so every pattern and both frameworks run unchanged on either:

  demo        data/shoes.json. Three demo stores with ordinary traps: a cheap black shoe that isn't a running
              shoe, a running shoe without size 9, and a ₹699 "Sparx" from a reseller nobody has checked.
  live        real listings from Amazon.in, Flipkart and Myntra, collected by patterns/live.py in your Chrome.
              Type and colour come from the evidence text. Size can't be seen on a search page, so it is not
              part of the query and stays unverified. The "seller register" becomes an evidence check: the
              store's own host, the product page read, not a search-index fallback, fresh.
  recording   the last live collection, replayed: for a stage without network. Labelled as recorded.

use(kind) switches the world in place, so modules that imported GOAL or LISTINGS see the new one.
use(query=...) swaps the shoe query for another one, parsed into the same goal fields. Live sites search for it
too (colour, type, budget); a recording replays whatever query it was collected for.
"""
import json
import re
import threading
from datetime import datetime
from pathlib import Path

DEMO = json.loads((Path(__file__).resolve().parent.parent / "data" / "shoes.json").read_text(encoding="utf-8"))
HOSTS = {"Amazon": "amazon.in", "Flipkart": "flipkart.com", "Myntra": "myntra.com"}

UNKNOWN = {"verified": False, "note": "not in the seller register"}

GOAL, LISTINGS, SELLERS, EVENT, STORES, SOURCE = {}, {}, {}, {}, [], {}
QUERY = ""
_prices = {}
_dropped = threading.Event()


def use(kind="demo", progress=lambda text: None, headless=None, fresh=False, query=None, stop=lambda: False):
    """Switch the world. kind: demo, live (collect if the last collection is over 15 minutes old, or fresh=True)
    or recording. headless: hide Chrome while collecting (None: MARKETPLACE_BROWSER_HEADLESS, default shown).
    query: any query parse() understands (None: the default shoe query). Not for a recording.
    stop: checked during a live collection (live.Stopped when it says so)."""
    global QUERY
    if query and kind == "recording":
        raise ValueError("A recording replays the query it was collected for. Use Live sites to search for yours.")
    if kind == "demo":
        goal = parse(query) if query else dict(DEMO["goal"])
        listings, stores = DEMO["listings"], sorted({x["store"] for x in DEMO["listings"]})
        sellers = {**{x["seller"]: UNKNOWN for x in listings}, **DEMO["sellers"]}   # not in the register: unverified
        event = DEMO["event"] if goal == DEMO["goal"] else _demo_event(goal)
        source = {"kind": "demo", "label": "Demo stores"}
    else:
        from patterns import live
        want = parse(query) if query else dict(DEMO["goal"])
        evidence = live.latest(sample=kind == "recording")   # live never reuses the shipped sample
        if kind == "live" and (fresh or evidence is None or live.age_seconds(evidence) > live.FRESH_SECONDS
                               or evidence.get("query") != live.search_text(want)):   # another query: search again
            if not live.available():
                raise RuntimeError("Playwright is not installed: pip install -r requirements-live.txt")
            progress(f"Collecting live evidence in Chrome for “{live.search_text(want)}”: Amazon, Flipkart, Myntra…")
            evidence = live.collect(want, headless=headless, progress=progress, stop=stop)
        if evidence is None:
            raise RuntimeError("No recording yet. Run a live collection first.")
        goal, listings, sellers, event, stores = _from_evidence(evidence, recorded=kind == "recording")
        when = datetime.fromisoformat(evidence["observed_at"]).astimezone()
        source = {"kind": kind, "label": ("Live sites" if kind == "live" else "Live · recording") + f" · {when:%d %b %H:%M}",
                  "observed_at": evidence["observed_at"], "sites": evidence.get("sources", [])}
    GOAL.clear(), GOAL.update(goal)
    LISTINGS.clear(), LISTINGS.update({x["id"]: x for x in listings})
    SELLERS.clear(), SELLERS.update(sellers)
    EVENT.clear(), EVENT.update(event)
    STORES[:] = stores
    SOURCE.clear(), SOURCE.update(source)
    QUERY = goal["query"]
    reset()
    return SOURCE


COLOURS = {"black", "white", "grey", "gray", "blue", "navy", "red", "green", "brown", "pink", "yellow", "orange", "beige"}
TYPES = {"running": "running", "runner": "running", "runners": "running", "casual": "casual", "slip-on": "casual"}
EXAMPLES = [DEMO["goal"]["query"], "Grey running shoes, size 9, under ₹800", "Running shoes, size 10, under ₹1,200",
            "Casual shoes under ₹600"]   # the page's dropdown; each one teaches something different


def parse(query):
    """A query → the goal every pattern checks: colour, type, size, budget. A word it doesn't know is no requirement.

    "Black running shoes, size 9, under ₹1,000"  → black, running, size 9, ₹1,000
    "Grey running shoes under 800"               → grey, running, any size, ₹800
    """
    words = re.findall(r"[a-z]+(?:-[a-z]+)?", query.lower())
    colour = next((w for w in words if w in COLOURS), None)
    size = re.search(r"size\s*(\d+)", query, re.I)
    budget = re.search(r"(?:under|below|upto|up to|max|<)\s*(?:₹|rs\.?|inr)?\s*([\d,]+)", query, re.I)
    if not budget:
        raise ValueError(f"Say a budget in the query, e.g. “{query.strip()} under ₹1,000”.")
    return {"query": query.strip(), "color": "grey" if colour == "gray" else colour,
            "type": next((TYPES[w] for w in words if w in TYPES), None),
            "size": int(size.group(1)) if size else None, "max_price": int(budget.group(1).replace(",", ""))}


def _demo_event(goal):
    """Level 3's price drop for another query: a verified listing that meets it, cheapest over budget first, drops
    about 15% (to under budget). Nothing meets the query: no event, and the watcher has nothing to watch."""
    ok = [x for x in DEMO["listings"] if DEMO["sellers"].get(x["seller"], UNKNOWN)["verified"]
          and (goal["type"] is None or x["type"] == goal["type"]) and (goal["color"] is None or x["color"] == goal["color"])
          and (goal["size"] is None or goal["size"] in x["sizes"])]
    over = [x for x in ok if x["price"] > goal["max_price"]]
    x = min(over or ok, key=lambda x: x["price"], default=None)
    if x is None:
        return {}
    new = min(x["price"], goal["max_price"]) * 85 // 100 // 10 * 10 - 1      # ₹1,349 → ₹1,139, ₹749 → ₹629
    return {"id": x["id"], "old_price": x["price"], "new_price": new}


def _from_evidence(ev, recorded):
    """Map the collector's candidates onto listings. Nothing is invented: unknown stays unknown."""
    from patterns import live
    budget = ev.get("budget", DEMO["goal"]["max_price"])
    want = ev.get("goal") or {"color": "black", "type": "running"}        # older collections were all this query
    goal = {"query": f"{live.words(want).capitalize()} under ₹{budget:,}", "color": want.get("color"),
            "type": want.get("type"), "size": None, "max_price": budget}
    kinds = [w for w, t in TYPES.items() if t == goal["type"]]
    listings, sellers = [], {}
    for c in ev["candidates"]:
        lines = []                       # brand and name, up to the first line that carries a price
        for line in c["product_name"].splitlines():
            if "₹" in line or "%" in line:
                break
            lines.append(line)
        name = " ".join(" ".join(lines).split())[:90] or c["marketplace"] + " listing"
        text = (c["product_name"] + " " + c.get("source_excerpt", "")[:400]).lower()
        problems = []
        if not live.on_host(c["source_url"], HOSTS[c["marketplace"]]):
            problems.append("not on the store's own site")
        if c.get("evidence_mode") == "search_index_fallback":
            problems.append("seen only in a search engine's index")
        if c.get("detail_status") != "OBSERVED":
            problems.append("product page not read")
        if not recorded and (datetime.now().astimezone() - datetime.fromisoformat(c["observed_at"])).total_seconds() > live.FRESH_SECONDS:
            problems.append("evidence older than 15 minutes")
        listings.append({"id": c["offer_id"], "store": c["marketplace"], "name": name, "price": round(c["observed_price_inr"]),
                         "type": goal["type"] if any(w in text for w in kinds) else "other" if goal["type"] else "any",
                         "color": goal["color"] if goal["color"] and goal["color"] in text else "other" if goal["color"]
                         else "any",
                         "sizes": None, "seller": c["offer_id"], "url": c["source_url"],
                         "evidence": "product page read" if c.get("detail_status") == "OBSERVED" else
                                     "search index" if c.get("evidence_mode") == "search_index_fallback" else "search page"})
        sellers[c["offer_id"]] = {"verified": not problems,
                                  "note": "; ".join(problems) if problems else f"{c['marketplace']} product page, read just now"
                                  if not recorded else f"{c['marketplace']} product page (recorded)"}
    stores = [s["marketplace"] for s in ev.get("sources", [])] or sorted(HOSTS)
    ok = [x for x in listings if sellers[x["id"]]["verified"] and x["price"] <= budget] or listings or [None]
    pick = min(ok, key=lambda x: x["price"]) if ok[0] else None
    # There is no real price feed: in a live world the event is a scheduled re-check of the stores.
    event = {"id": pick["id"], "old_price": pick["price"], "new_price": pick["price"]} if pick else {}
    return goal, listings, sellers, event, stores


def reset():
    _prices.clear()
    _prices.update({i: x["price"] for i, x in LISTINGS.items()})
    _dropped.clear()


def name(lid):
    return LISTINGS[lid]["name"] if lid in LISTINGS else str(lid)


def price(lid):
    return _prices.get(lid, LISTINGS[lid]["price"])


def label(lid):
    return f"{name(lid)} · ₹{price(lid):,} · {LISTINGS[lid]['store']}" if lid in LISTINGS else str(lid)


def view():
    """What the page draws in its store panel."""
    return [{**x, "price": price(x["id"])} for x in LISTINGS.values()]


def item_text(plural=True):
    """The goal's colour and type in words: "black running shoes"."""
    return " ".join(w for w in (GOAL.get("color"), GOAL.get("type"), "shoes" if plural else "shoe") if w)


def size_text():
    return f"size {GOAL['size']}" if GOAL.get("size") else "size (unverified)"


def keyword():
    """The one word the Level 0 developer put in the script's search box: the query's colour, or else its type."""
    return GOAL.get("color") or GOAL.get("type") or "shoe"


def dropped_text():
    """What a script that only searches for keyword() and checks the price silently drops."""
    left = [f"“{w}”" for w in (GOAL.get("color"), GOAL.get("type")) if w and w != keyword()]
    left += [f"“size {GOAL['size']}”"] if GOAL.get("size") else []
    return " or ".join(left) or "nothing else"


def fits(lid):
    """Does a listing meet the query (type, colour, size, budget)? The seller is a separate check."""
    x, g = LISTINGS[lid], GOAL
    return ((g.get("type") is None or x["type"] == g["type"]) and (g.get("color") is None or x["color"] == g["color"])
            and in_stock(lid, g.get("size")) and price(lid) <= g["max_price"])


def proposal(lid):
    """What checkout asks the human, in this world."""
    x = LISTINGS[lid]
    if SOURCE.get("kind") == "demo":
        return f"Verified seller, size {GOAL['size']} in stock, {x['store']}. Buy it?"
    return (f"Product page read on {x['store']}. Size, stock, delivery and the checkout total are not verified: "
            "check them before you buy.")


def event_text(e):
    if e["old_price"] != e["new_price"]:
        return f"{e['name']}: ₹{e['old_price']:,} → ₹{e['new_price']:,}"
    return f"scheduled re-check: {e['name']} at ₹{e['new_price']:,}"


# ---------------------------------------------------------------- tools

def search_catalog(keyword):
    """Keyword search over listing names, the way a store's search box works."""
    return [i for i, x in LISTINGS.items() if keyword.lower() in x["name"].lower()]


def search_store(store, kind=None, color=None):
    """One store's listings, optionally by type and colour (None: any)."""
    return [i for i, x in LISTINGS.items() if x["store"] == store
            and (kind is None or x["type"] == kind) and (color is None or x["color"] == color)]


def in_stock(lid, size):
    """No size in the query (live sites): nothing to check. A size the page can't show stays unverified."""
    if size is None:
        return True
    return LISTINGS[lid]["sizes"] is not None and size in LISTINGS[lid]["sizes"]


def seller_check(lid):
    s = LISTINGS[lid]["seller"]
    return {"seller": s if SOURCE.get("kind") == "demo" else LISTINGS[lid]["store"], **SELLERS[s]}


# ---------------------------------------------------------------- the price feed (Level 3)

def drop_price():
    if EVENT:
        _prices[EVENT["id"]] = EVENT["new_price"]
    _dropped.set()


def wait_for_drop(timeout=None):
    """Block until the price drops (live: until the scheduled re-check). Returns the event, or None on timeout."""
    if not _dropped.wait(timeout) or not EVENT:
        return None
    return {**EVENT, "name": name(EVENT["id"]), "store": LISTINGS[EVENT["id"]]["store"]}


use("demo")
