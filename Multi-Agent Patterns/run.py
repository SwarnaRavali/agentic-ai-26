"""Run the agent team.

Act 1 · watch it work (all guardrails on)
  python run.py                          the price drops at once
  python run.py --watch                  wait for a real price change (python run.py --drop in a 2nd terminal)
  python run.py --auto-drop 3            the price drops by itself after 3 seconds

Act 3 · remove a guardrail
  python run.py --no-owner               both agents buy: 2 items in the cart
  python run.py --no-budget --chaos      the owner re-checks forever until the framework kills it
  python run.py --chaos                  same loop, budget on: stops at 6 turns and escalates
  python run.py --no-approval            it buys and nobody was asked
  python run.py --unsafe                 all three off

Act 4 · crash, resume, rewind
  python run.py --crash-after evaluator  the process dies mid-run
  python run.py --resume                 carry on from the last checkpoint; finished agents don't re-run
  python run.py --history                list the last run's checkpoints
  python run.py --rewind N               replay from checkpoint N with all guardrails on (or name some to remove)

Settings come from .env (copy .env.example). Real environment variables win.
Each run writes console.log, e2e.log, diff.log and summary.json to output/<timestamp>_<label>/.
"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # ₹ in help and output, even when piped on Windows

import argparse

from lab import runner


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--no-owner", action="store_true", help="remove guardrail 1: one owner per task")
    p.add_argument("--no-budget", action="store_true", help="remove guardrail 2: budget and stop")
    p.add_argument("--no-approval", action="store_true", help="remove guardrail 3: human approval")
    p.add_argument("--unsafe", action="store_true", help="remove all three guardrails")
    p.add_argument("--chaos", action="store_true", help="the owner agent keeps re-checking prices forever")
    p.add_argument("--watch", action="store_true", help="wait for a price change in the feed")
    p.add_argument("--auto-drop", type=float, default=None, help="seconds until the price drops by itself")
    p.add_argument("--yes", action="store_true", help="approve without asking (for testing)")
    p.add_argument("--deny", action="store_true", help="deny without asking (for testing)")
    p.add_argument("--crash-after", choices=["watcher", "scout", "evaluator", "deal", "budget"],
                   help="kill the process right after this agent")
    p.add_argument("--resume", action="store_true", help="carry on the last run from its last checkpoint")
    p.add_argument("--history", action="store_true", help="list the last run's checkpoints")
    p.add_argument("--rewind", type=int, metavar="N", help="replay the last run from checkpoint N")
    p.add_argument("--drop", action="store_true", help="drop the Sparx shoe to ₹849 in the feed, then exit")
    p.add_argument("--reset-feed", action="store_true", help="put every price back above budget, then exit")
    a = p.parse_args()
    answer = "approve" if a.yes else "deny" if a.deny else None

    if a.drop or a.reset_feed:
        from lab import feed
        feed.reset_feed() if a.reset_feed else feed.drop_price()
        print("Feed reset: all prices above budget." if a.reset_feed else "Sparx black running shoe → ₹849")
    elif a.history:
        runner.history()
    elif a.resume:
        runner.resume(answer=answer)
    elif a.rewind is not None:
        runner.rewind(a.rewind, owner=not (a.no_owner or a.unsafe), budget=not (a.no_budget or a.unsafe),
                      approval=not (a.no_approval or a.unsafe), chaos=a.chaos, answer=answer)
    else:
        runner.run(owner=not (a.no_owner or a.unsafe), budget=not (a.no_budget or a.unsafe),
                   approval=not (a.no_approval or a.unsafe), chaos=a.chaos, watch=a.watch, auto_drop=a.auto_drop,
                   answer=answer, crash_after=a.crash_after)


if __name__ == "__main__":
    main()
