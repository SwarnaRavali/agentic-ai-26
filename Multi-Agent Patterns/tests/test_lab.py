"""Smoke tests: every mode of the lab, offline, at full speed.  Run: python -m pytest -q"""
import os
import subprocess
import sys

import pytest
from conftest import ROOT

from lab import feed, runner


@pytest.fixture(autouse=True)
def clean_feed():
    yield
    feed.reset_feed()


def test_all_guardrails_on_buys_one_approved_item():
    state, logs = runner.run(answer="approve")
    assert len(state["cart"]) == 1
    assert state["outcome"] == "Bought 1 item, approved by a human."
    assert len(state["offers"]) == len(feed.DEFAULT_ITEMS)   # one scout per store
    for name in ("console.log", "e2e.log", "diff.log", "summary.json"):
        assert (logs / name).stat().st_size > 0
    assert "scout + scout + scout" in (logs / "diff.log").read_text(encoding="utf-8")


def test_deny_cancels():
    state, _ = runner.run(answer="deny")
    assert state.get("cart", []) == []
    assert state["outcome"] == "Cancelled by a human."


def test_no_owner_buys_twice_then_budget_stops_it():
    state, _ = runner.run(owner=False, answer="approve")
    assert len(state["cart"]) == 2
    assert state["outcome"].startswith("Stopped by budget")


def test_no_budget_loop_is_killed_by_the_framework():
    state, _ = runner.run(budget=False, chaos=True, answer="approve")
    assert state.get("cart", []) == []
    assert state["turn"] > 6


def test_budget_stops_the_loop():
    state, _ = runner.run(chaos=True, answer="approve")
    assert state["turn"] == 6
    assert state["outcome"].startswith("Stopped by budget")


def test_no_approval_buys_without_asking():
    state, _ = runner.run(approval=False)
    assert state["outcome"] == "Bought 1 item. Nobody approved it."


def test_crash_then_resume_skips_finished_agents():
    crashed = subprocess.run([sys.executable, "run.py", "--crash-after", "evaluator"], cwd=ROOT,
                             env={**os.environ, "PYTHONIOENCODING": "utf-8"}, capture_output=True)
    assert crashed.returncode == 1
    state, logs = runner.resume(answer="approve")
    assert len(state["cart"]) == 1
    e2e = (logs / "e2e.log").read_text(encoding="utf-8")
    assert '"node": "scout"' not in e2e and '"node": "deal"' in e2e   # scouts were not re-run


def test_rewind_a_bad_run_with_guardrails_on():
    runner.run(owner=False, budget=False, approval=False)
    before_deal = next(n for n, snap in runner.history(show=False) if snap.next == ("deal",))
    state, logs = runner.rewind(before_deal, answer="approve")
    assert len(state["cart"]) == 1
    assert '"node": "scout"' not in (logs / "e2e.log").read_text(encoding="utf-8")
