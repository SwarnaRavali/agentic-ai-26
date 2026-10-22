"""Level 3 in CrewAI · a Flow. Nobody types anything.

    @start wait_for_price → @router does_it_matter → @listen("trigger") run_team (the Level 2 crew)

A Flow is CrewAI's event-driven layer: methods start when the methods they listen to finish, and a router
returns the name of the next branch. Here the first method waits for the price feed; the router asks the
watcher (one model call) whether the change matters; the listener runs the Level 2 crew, which asks you
before it buys.
"""
from crewai.flow.flow import Flow, listen, router, start
from pydantic import BaseModel

from crews import l2_guardrail as l2
from crews.contracts import Decision
from lab import llm
from patterns import common as c
from patterns import world

TITLE = "Level 3 · Flow"
HUMAN_STEPS = 0


class Watch(BaseModel):
    auto_drop: float | None = 6.0
    event: dict = {}
    pick: str | None = None
    answer: str = ""


class PriceWatch(Flow[Watch]):
    @start()
    def wait_for_price(self):
        c.status("lead", "active", "watching the feed")
        c.emit("waiting", auto_drop=self.state.auto_drop)
        event = world.wait_for_drop(self.state.auto_drop)
        if event is None:                      # nobody dropped it in time: the feed does it
            world.drop_price()
            event = world.wait_for_drop(0)
        if event is None:
            c.note("Nothing in the stores is under budget. The watcher goes back to sleep.")
            return
        self.state.event = event
        c.emit("price", id=event["id"], old=event["old_price"], new=event["new_price"])
        c.step("Something changes in the world")
        c.msg("feed", "lead", "event", world.event_text(event))

    @router(wait_for_price)
    def does_it_matter(self):
        e = self.state.event
        if not e:
            return "ignore"
        c.status("lead", "active", "thinking…")
        answer, tokens = llm.structured(
            "lead", f"You are a watcher. Saved query: {world.QUERY}. Price change: {e['name']} "
                    f"₹{e['old_price']} → ₹{e['new_price']}. Does it matter? action: trigger or ignore.",
            Decision.model_json_schema(),
            lambda: {"action": "trigger", "reason": f"{e['name']} is now ₹{e['new_price']:,}, under budget. "
                                                    "Waking the team."} if world.fits(e["id"]) else
                    {"action": "ignore", "reason": f"{e['name']} doesn't meet the saved query."})
        c.counted("lead", tokens)
        d = Decision.model_validate(answer)
        c.say("lead", d.reason)
        return "trigger" if d.action == "trigger" else "ignore"

    @listen("trigger")
    def run_team(self):
        out = l2.run_team(ask_first=True)
        self.state.pick, self.state.answer = out["pick"], out["answer"]


def run(auto_drop=6.0):
    l2.team("Watcher · Flow")
    c.step("No prompt. A Flow's @start method waits for the price feed")
    flow = PriceWatch()
    flow.kickoff(inputs={"auto_drop": auto_drop})
    if flow.state.pick is None:
        c.note("The watcher decided it doesn't matter. Back to sleep.")
        return {"pick": None, "answer": "ignored"}
    c.step("You hear about it only when there is something to decide")
    return {"pick": flow.state.pick, "answer": flow.state.answer}
