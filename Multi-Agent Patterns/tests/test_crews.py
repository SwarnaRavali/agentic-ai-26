"""Demo 1 built with CrewAI: the same four patterns, the same purchases. Skipped if CrewAI isn't installed."""
import pytest

import crews
import patterns
from lab import llm
from patterns import common

pytestmark = pytest.mark.skipif(not crews.available(), reason="pip install -r requirements-crewai.txt")


@pytest.fixture(scope="module")
def results():
    return {n: crews.run(n, auto_drop=0.05) for n in range(4)}


def test_crewai_buys_the_same_shoes_as_langgraph(results):
    for n, r in results.items():
        assert r["framework"] == "crewai"
        assert r["grade"]["pick"] == patterns.run(n, auto_drop=0.05)["grade"]["pick"]
    assert [results[n]["grade"]["score"] for n in range(4)] == [2, 3, 4, 4]


def test_every_crewai_step_is_a_model_call(results):
    # In LangGraph a step can be plain code; in a crew every task is an agent turn.
    assert [results[n]["stats"]["llm_calls"] for n in range(4)] == [3, 5, 5, 6]


def test_the_guardrail_rejects_the_fake_and_the_evaluator_retries():
    seen = []
    stop = common.listen(seen.append)
    try:
        crews.run(2)
    finally:
        stop()
    flags = [e for e in seen if e["type"] == "msg" and e["kind"] == "flag"]
    assert len(flags) == 1 and flags[0]["from"] == "critic"
    calls = [e["agent"] for e in seen if e["type"] == "tokens"]
    assert calls.count("evaluator") == 2                     # the first pick, then the retry with feedback


def test_a_failing_model_falls_back_to_the_script(monkeypatch):
    from lab import claude_cli
    monkeypatch.setattr(llm, "MODE", "claude")
    monkeypatch.setattr(claude_cli, "infer", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no login")))
    try:
        r = crews.run(0)
    finally:
        llm.configure("offline")
    assert r["grade"]["pick"] == "a2"


def test_crewai_follows_another_query():
    from patterns import world
    world.use("demo", query="Running shoes size 10 under 1200")
    try:
        picks = [crews.run(n, auto_drop=0.05)["grade"]["pick"] for n in range(3)]
    finally:
        world.use("demo")
    assert picks == ["c3", "c2", "c2"]     # L0 searches "running" and drops size 10 and the seller check
