"""Level 3 · Event-driven. Nobody types anything.

    price feed ─event→ watcher ─→ [the Level 2 team] → asks you before it buys

Communication: publish/subscribe. A watcher subscribes to the price feed with the saved query.
When a price change matters, the watcher starts the Level 2 team, unchanged. The team finds the
dropped Sparx, the critic checks the seller, and checkout asks you instead of ordering.
"""
from patterns import common as c
from patterns import l2_team as l2
from patterns import world

TITLE = "Level 3 · Event-driven"
HUMAN_STEPS = 0


def run(auto_drop=6.0):
    """Waits for a price drop in the feed. auto_drop: seconds until it drops by itself (None: wait forever)."""
    l2.team("Watcher")
    c.step("No prompt. The watcher is subscribed to the price feed with your saved query" if world.SOURCE["kind"] == "demo"
           else "No prompt. A schedule wakes the watcher to re-check the live sites")
    c.status("lead", "active", "watching the feed")
    c.emit("waiting", auto_drop=auto_drop)
    event = world.wait_for_drop(auto_drop)
    if event is None:                      # nobody dropped it in time: the feed does it
        world.drop_price()
        event = world.wait_for_drop(0)
    if event is None:
        c.note("Nothing in the stores is under budget. The watcher goes back to sleep.")
        return {"pick": None, "answer": "Nothing to watch."}
    c.emit("price", id=event["id"], old=event["old_price"], new=event["new_price"])
    c.step("Something changes in the world")
    c.msg("feed", "lead", "event", world.event_text(event))
    reply = c.think("lead", "You are a watcher. Decide whether this price change matters for the saved query.",
                    {"event": event, "saved_query": world.GOAL}, ["trigger", "ignore"],
                    offline={"action": "trigger", "say": f"{event['name']} is now ₹{event['new_price']:,}, under "
                                                         "budget. Waking the team."} if world.fits(event["id"]) else
                            {"action": "ignore", "say": f"{event['name']} doesn't meet the saved query."})
    c.say("lead", reply["say"])
    if reply["action"] != "trigger":
        c.note("The watcher decided it doesn't matter. Back to sleep.")
        return {"pick": None, "answer": reply["say"]}
    out = l2.build().invoke({"query": world.QUERY, "ask_first": True})
    c.step("You hear about it only when there is something to decide")
    return out
