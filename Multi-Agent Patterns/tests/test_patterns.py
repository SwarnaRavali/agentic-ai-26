"""Part 2: one shoe query, four patterns. Offline, at full speed.  Run: python -m pytest -q"""
import json
import threading
import urllib.request

import pytest

import patterns
from lab import llm
from patterns import common, l1_orchestrator, l2_team, score, world


@pytest.fixture(scope="module")
def results():
    return {n: patterns.run(n, auto_drop=0.05) for n in patterns.LEVELS}


def test_the_purchase_improves_with_the_pattern(results):
    g = {n: r["grade"] for n, r in results.items()}
    assert [g[n]["pick"] for n in range(4)] == ["a2", "c3", "c2", "a1"]
    assert [g[n]["score"] for n in range(4)] == [2, 3, 4, 4]
    assert g[3]["price"] == world.EVENT["new_price"] < g[2]["price"]   # the event found it cheaper


def test_what_each_level_misses(results):
    miss = {n: [k for k, ok in r["grade"]["checks"].items() if not ok] for n, r in results.items()}
    assert miss[0] == ["black running shoe", "size 9 in stock"]     # the script never checks them
    assert miss[1] == ["genuine seller"]                            # nobody's brief is about the seller
    assert miss[2] == miss[3] == []
    assert [results[n]["stats"]["human_steps"] for n in range(4)] == [4, 1, 1, 0]


def test_level2_scouts_run_in_parallel_and_the_critic_sends_the_pick_back():
    seen = []
    stop = common.listen(seen.append)
    try:
        patterns.run(2)
    finally:
        stop()
    tasks = [e["to"] for e in seen if e["type"] == "msg" and e["kind"] == "task" and e["from"] == "lead"]
    assert tasks == ["scout-" + s for s in world.STORES] or sorted(tasks) == ["scout-" + s for s in world.STORES]
    flags = [e for e in seen if e["type"] == "msg" and e["kind"] == "flag"]
    assert len(flags) == 1 and flags[0]["from"] == "critic" and flags[0]["to"] == "evaluator"
    assert any(e["type"] == "listing" and e["state"] == "rejected" and e["ids"] == ["c3"] for e in seen)


def test_without_the_critic_level2_buys_the_fake(monkeypatch):
    monkeypatch.setattr(l2_team, "after_evaluator", lambda state: "checkout")
    assert patterns.run(2)["grade"]["pick"] == "c3"


def test_a_seller_missing_from_the_register_counts_as_unverified(monkeypatch):
    shoe = {"id": "b4", "store": "demo-store-b", "name": "Campus black running shoe", "price": 599, "type": "running",
            "color": "black", "sizes": [8, 9], "seller": "QuickKicks"}     # the README's exercise, seller not registered
    monkeypatch.setitem(world.DEMO, "listings", world.DEMO["listings"] + [shoe])
    world.use("demo")
    try:
        assert [patterns.run(n, auto_drop=0.05)["grade"]["pick"] for n in range(3)] == ["a2", "b4", "c2"]
        assert score.grade("b4")["checks"]["genuine seller"] is False
    finally:
        monkeypatch.undo()
        world.use("demo")


def test_a_worker_added_to_level1_gets_planned(monkeypatch):
    monkeypatch.setitem(l1_orchestrator.SKILLS, "seller", "drop listings from unverified sellers")
    monkeypatch.setattr(l1_orchestrator, "PLAN", ["search", "size", "price", "seller", "pick"])
    with pytest.raises(NotImplementedError, match="seller"):   # planned, so its missing branch shows up at once
        patterns.run(1)


def test_grader():
    assert score.grade("c2")["score"] == 4
    assert score.grade("b2")["checks"]["size 9 in stock"] is False
    assert score.grade("c3")["checks"]["genuine seller"] is False


def test_bad_model_action_falls_back_to_the_script(monkeypatch):
    monkeypatch.setattr(llm, "MODE", "claude")
    monkeypatch.setattr(llm, "_real", lambda *a, **k: ({"action": "not-a-shoe", "say": "?"}, 10))
    reply, _ = llm.ask("x", "role", {}, ["a", "b"], offline={"action": "b", "say": "scripted"})
    assert reply["action"] == "b" and "scripted" in reply["say"]


def test_live_server_runs_a_level_and_streams_it():
    from patterns import server as live
    server = live.make_server(0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        code = json.load(urllib.request.urlopen(base + "/code?level=2"))
        assert code["file"] == "patterns/l2_team.py" and "Send(" in code["code"]
        req = urllib.request.Request(base + "/run", data=json.dumps({"level": 1, "pace": 0}).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req)
        with urllib.request.urlopen(base + "/events", timeout=30) as stream:
            for line in stream:
                if line.startswith(b"data: "):
                    ev = json.loads(line[6:])
                    if ev["type"] == "run_start":
                        assert len(ev["listings"]) == len(world.LISTINGS)
                    if ev["type"] == "run_end":
                        assert ev["grade"]["pick"] == "c3"
                    if ev["type"] in ("idle", "error"):
                        assert ev["type"] == "idle"
                        break
    finally:
        live.SESSION.stop()
        server.shutdown()
        server.server_close()


def test_a_paused_run_holds_still_then_finishes():
    import time
    seen, done = [], []
    stop = common.listen(seen.append)
    common.set_pace(0.05)                     # a real pace, so the pause lands mid-run
    t = threading.Thread(target=lambda: done.append(patterns.run(2)))
    try:
        t.start()
        while len(seen) < 5:
            time.sleep(0.01)
        common.pause(True)
        time.sleep(0.3)
        held = len(seen)
        time.sleep(0.6)
        assert len(seen) <= held + 1          # at most one event already past the check
        assert not done
        common.pause(False)
        t.join(10)
        assert done and done[0]["grade"]["pick"] == "c2"
    finally:
        common.pause(False)
        common.set_pace(0)
        stop()


def test_stop_works_while_paused():
    import time
    seen, errors = [], []
    stop = common.listen(seen.append)

    def runner():
        try:
            patterns.run(1)
        except common.Cancelled:
            errors.append("cancelled")
    common.set_pace(0.05)
    t = threading.Thread(target=runner)
    try:
        t.start()
        while len(seen) < 3:
            time.sleep(0.01)
        common.pause(True)
        time.sleep(0.2)
        common.cancel()
        t.join(5)
        assert errors == ["cancelled"]
    finally:
        common.pause(False)
        common.set_pace(0)
        common.rearm()
        stop()


def test_stop_before_the_first_level_starts_holds():
    from patterns import server
    common.set_pace(0.05)
    n = len(server.SESSION.log.events)
    try:
        server.SESSION.launch([0, 1], "langgraph", None, 0.05, 0)
        server.SESSION.stop()                               # pressed straight away: nothing is bought
        server.SESSION.thread.join(10)
    finally:
        common.set_pace(0)
        common.rearm()
    kinds = [e["type"] for e in server.SESSION.log.events[n:]]
    assert kinds[0] == "launched" and "stopped" in kinds and "run_end" not in kinds


def test_every_model_call_reaches_the_page_and_the_run_log(monkeypatch, tmp_path):
    monkeypatch.setattr(common, "LOGS", tmp_path)   # this test reads the file it writes
    seen = []
    stop = common.listen(seen.append)
    try:
        patterns.run(1)
    finally:
        stop()
    calls = [e for e in seen if e["type"] == "llm"]
    assert len(calls) == sum(e["type"] == "tokens" for e in seen) > 0
    assert all("reply" in e and "context" in e for e in calls)
    lines = [json.loads(x) for x in next(tmp_path.glob("*_langgraph_L1_demo.jsonl")).read_text(encoding="utf-8").splitlines()]
    assert lines[0]["type"] == "run_start" and lines[-1]["type"] == "run_end"
    assert [x["type"] for x in lines] == [e["type"] for e in seen]
    assert lines[-1]["t"] >= lines[0]["t"] == 0


def test_a_query_becomes_the_goal():
    assert world.parse(world.DEMO["goal"]["query"]) == world.DEMO["goal"]
    assert all(world.parse(q)["max_price"] for q in world.EXAMPLES)       # every example on the page runs
    assert world.parse("Grey running shoes under 800") == {"query": "Grey running shoes under 800", "color": "grey",
                                                           "type": "running", "size": None, "max_price": 800}
    with pytest.raises(ValueError, match="budget"):
        world.parse("black shoes")
    with pytest.raises(ValueError, match="recording"):
        world.use("recording", query="Grey running shoes under 800")


@pytest.fixture
def grey():
    world.use("demo", query="Grey running shoes, size 9, under ₹800")
    yield
    world.use("demo")


def test_another_query_runs_through_every_level(grey):
    r = {n: patterns.run(n, auto_drop=0.05) for n in patterns.LEVELS}
    assert [r[n]["grade"]["pick"] for n in range(3)] == ["b3"] * 3          # the only grey running shoe
    assert list(r[0]["grade"]["checks"]) == ["grey running shoe", "size 9 in stock", "under ₹800", "genuine seller"]
    assert r[3]["grade"]["pick"] == "b3" and r[3]["grade"]["price"] == 629   # the feed drops a shoe that fits this query
    world.use("demo", query="White running shoes under ₹2,000")
    assert world.EVENT == {} and patterns.run(3, auto_drop=0.05)["grade"] is None   # nothing fits: nothing to watch


def test_reset_all_goes_back_to_the_default_page():
    from patterns import server
    world.use("demo", query="Grey running shoes under ₹800")
    server.SESSION.results = {("demo", "langgraph", 0): {}}
    server.SESSION.reset()
    assert server.SESSION.results == {} and world.QUERY == world.DEMO["goal"]["query"]
    log = server.SESSION.log
    assert log.events[log.start:] == [] and log.events[-1]["type"] == "reset"   # a reloaded page replays nothing
