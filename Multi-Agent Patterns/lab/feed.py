"""A tiny fake store feed.

The "world" is one JSON file, output/price_feed.json, created on first use. A watcher polls it.
When a price drops under the saved goal's budget, that is an event, and the agents start.
No prompt, no form. Change it from a second terminal with: python run.py --drop
"""
import json
import os
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORLD = json.loads((ROOT / "data" / "shoes.json").read_text(encoding="utf-8"))   # the same stores as Part 2
FEED = Path(os.getenv("LAB_OUTPUT") or ROOT / "output") / "price_feed.json"   # changes during the demo, so it lives with the run logs

# The user saved this goal earlier. Nobody is typing during the demo.
GOAL = {"item": "black running shoes", "max_price": WORLD["goal"]["max_price"]}

# One listing per store, all above budget until the price drops.
DEFAULT_ITEMS = [{"sku": x["id"], "name": x["name"], "price": x["price"], "store": x["store"]}
                 for x in WORLD["listings"] if x["id"] in WORLD["guardrails_lab"]]
EVENT = WORLD["event"]


def read_feed(retries=20):
    if not FEED.exists():
        reset_feed()
    # Retry: an editor or another process may be halfway through saving the file.
    for _ in range(retries):
        try:
            return json.loads(FEED.read_text())["items"]
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            time.sleep(0.05)
    raise RuntimeError(f"Could not read {FEED}. Is it valid JSON? Run: python run.py --reset-feed")


def write_feed(items):
    # Write to a temp file, then swap it in, so readers never see half a file.
    FEED.parent.mkdir(parents=True, exist_ok=True)
    tmp = FEED.with_suffix(".tmp")
    tmp.write_text(json.dumps({"items": items}, indent=2) + "\n")
    for _ in range(20):   # Windows: a reader (the lab page's feed watcher) can hold the file for a moment
        try:
            os.replace(tmp, FEED)
            return
        except PermissionError:
            time.sleep(0.05)
    os.replace(tmp, FEED)


def reset_feed():
    """Put every price back above budget so the demo is repeatable."""
    write_feed([dict(i) for i in DEFAULT_ITEMS])


def drop_price(sku=EVENT["id"], price=EVENT["new_price"]):
    items = read_feed()
    for item in items:
        if item["sku"] == sku:
            item["price"] = price
    write_feed(items)


def find_event(before, after):
    """An event = an item that just crossed under the goal budget."""
    old = {i["sku"]: i["price"] for i in before}
    for item in after:
        was = old.get(item["sku"])
        if was is not None and was > GOAL["max_price"] >= item["price"]:
            return {**item, "old_price": was, "goal": GOAL}
    return None


def watch(poll=0.5, auto_drop=None):
    """Block until an event happens. Returns the event dict.

    auto_drop: seconds after which the price drops by itself (single-screen demo).
    """
    baseline = read_feed()
    if auto_drop is not None:
        threading.Timer(auto_drop, drop_price).start()
    while True:
        time.sleep(poll)
        current = read_feed()
        event = find_event(baseline, current)
        if event:
            return event
        baseline = current
