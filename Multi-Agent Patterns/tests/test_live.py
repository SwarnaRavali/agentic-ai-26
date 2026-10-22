"""The live world, without the network: the recording shipped in data/live-sample.json, and the collector's
pure helpers. A real collection needs Chrome and the sites, so it is not part of the test run."""
import json
from datetime import datetime, timezone

import pytest

import patterns
from patterns import live, score, world


@pytest.fixture(autouse=True)
def sample_only(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "OUT", tmp_path)          # no real collections: only the shipped recording
    yield
    world.use("demo")


def test_the_recording_becomes_a_world():
    src = world.use("recording")
    assert src["kind"] == "recording" and world.STORES == ["Amazon", "Flipkart", "Myntra"]
    assert world.GOAL["size"] is None                   # a search page can't show size: not in the query
    assert world.QUERY == "Black running shoes under ₹1,000"
    blue = next(x for x in world.LISTINGS.values() if "Blue" in x["name"])
    assert blue["color"] != "black"                     # a real trap: blue sneakers in a "black" search
    unverified = [i for i, s in world.SELLERS.items() if not s["verified"]]
    assert unverified and all("product page not read" in world.SELLERS[i]["note"] for i in unverified)


def test_every_pattern_runs_on_live_evidence():
    world.use("recording")
    g = {n: patterns.run(n, auto_drop=0.05)["grade"] for n in range(4)}
    assert all(r is not None and r["of"] == 4 for r in g.values())
    assert "cheapest match" not in [k for k, ok in g[2]["checks"].items() if ok] or g[2]["score"] == 4
    assert g[0]["checks"]["cheapest match"] is False    # the script's cheapest "black" name isn't the best match
    assert g[2]["score"] == g[3]["score"] == 4


def test_grade_rejects_an_invented_listing():
    world.use("recording")
    assert score.grade("AMA-not-a-listing") is None


def test_live_reuses_a_fresh_collection_and_collects_a_stale_one(monkeypatch, tmp_path):
    sample = json.loads(live.SAMPLE.read_text(encoding="utf-8"))
    calls = []
    monkeypatch.setattr(live, "available", lambda: True)
    monkeypatch.setattr(live, "collect", lambda goal, **kw: calls.append(goal["max_price"]) or fresh)
    fresh = {**sample, "observed_at": datetime.now(timezone.utc).isoformat()}
    stale = {**sample, "observed_at": "2026-01-01T00:00:00+00:00"}
    (tmp_path / "latest.json").write_text(json.dumps(stale), encoding="utf-8")        # old: must collect
    world.use("live")
    assert calls == [1000]
    (tmp_path / "latest.json").write_text(json.dumps(fresh), encoding="utf-8")        # fresh: reuse
    world.use("live")
    assert calls == [1000]
    world.use("live", fresh=True)                                                      # the page's "Collect fresh"
    assert calls == [1000, 1000]
    world.use("live", query="Grey running shoes under ₹800")                           # another query: search again
    assert calls == [1000, 1000, 800]


def test_a_live_search_follows_the_query():
    goal = world.parse("Grey running shoes, size 9, under ₹800")
    assert live.search_text(goal) == "grey running shoes under 800"   # size can't be searched or seen: left out
    ev = {**json.loads(live.SAMPLE.read_text(encoding="utf-8")), "budget": 800, "goal": {"color": "grey", "type": "running", "max_price": 800}}
    g, listings, *_ = world._from_evidence(ev, recorded=True)
    assert g["query"] == "Grey running shoes under ₹800" and g["size"] is None
    assert {x["color"] for x in listings} <= {"grey", "other"}


def test_clear_forgets_the_collection_and_its_scores(tmp_path):
    from patterns import server
    (tmp_path / "latest.json").write_text(live.SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "amazon-latest.png").write_bytes(b"png")
    server.SESSION.results = {("demo", "langgraph", 0): {}, ("live", "langgraph", 0): {}, ("recording", "crewai", 1): {}}
    server.SESSION.clear_live()
    assert list(tmp_path.iterdir()) == [] and list(server.SESSION.results) == [("demo", "langgraph", 0)]
    assert live.latest() == json.loads(live.SAMPLE.read_text(encoding="utf-8"))   # recording: back to the sample


def test_the_evidence_page_shows_what_each_site_returned():
    from patterns import server
    page = server.evidence_page()
    assert "Live evidence" in page and "Flipkart" in page and "verified" in page
    assert "evidence/amazon-latest.png" in page


def test_collector_helpers():
    assert live.on_host("https://www.amazon.in/dp/B0BBG64HRD", "amazon.in")
    assert not live.on_host("https://amazon.in.evil.example/x", "amazon.in")
    assert not live.on_host("http://www.amazon.in/x", "amazon.in")                  # https only
    assert live.price_in("M.R.P. ₹1,399\n₹894.00", lowest=True) == 894
    assert live._clean_url("Amazon", "https://www.amazon.in/sspa/click?url=%2FShoe%2Fdp%2FB0BBG64HRD%2Fref%3Dx") == \
        "https://www.amazon.in/dp/B0BBG64HRD"
