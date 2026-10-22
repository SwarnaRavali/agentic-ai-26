"""The guardrails lab in the browser: start lab/server.py, drive runs through it the way the page does.  Run: python -m pytest -q"""
import json
import threading
import urllib.error
import urllib.request

import pytest

from lab import feed
from lab import server as ui


@pytest.fixture
def base():
    server = ui.make_server(0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    ui.SESSION.stop()
    server.shutdown()
    server.server_close()
    feed.reset_feed()


def post(base, path, body=None):
    req = urllib.request.Request(base + path, data=json.dumps(body or {}).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def run(base, args, answer="approve"):
    """Start a run and read the page's event stream until run.py exits, answering the approval like a click."""
    post(base, "/run", {"args": args, "delay": 0})
    seen = []
    with urllib.request.urlopen(base + "/events", timeout=60) as stream:
        for line in stream:
            if not line.startswith(b"data: "):
                continue
            ev = json.loads(line[6:])
            seen.append(ev)
            if ev["type"] == "e2e" and ev["kind"] == "interrupt":
                post(base, "/answer", {"answer": answer})
            if ev["type"] == "exit":
                return seen


def trace(seen, kind):
    return [ev["data"] for ev in seen if ev["type"] == "e2e" and ev["kind"] == kind]


def test_safe_run_approved_from_the_page(base):
    seen = run(base, [])
    assert seen[0]["type"] == "hello" and seen[1]["type"] == "start"
    nodes = [d["node"] for d in trace(seen, "node")]
    assert nodes.count("scout") == len(feed.DEFAULT_ITEMS) and "checkout" in nodes
    assert trace(seen, "run_end")[0]["outcome"] == "Bought 1 item, approved by a human."
    assert any(ev["type"] == "diff" for ev in seen) and any(ev["type"] == "console" for ev in seen)
    assert seen[-1]["code"] == 0


def test_crash_then_resume_then_checkpoints(base):
    crashed = run(base, ["--crash-after", "evaluator"])
    assert crashed[-1]["code"] == 1 and trace(crashed, "crash")
    resumed = run(base, ["--resume"])
    nodes = [d["node"] for d in trace(resumed, "node")]
    assert "scout" not in nodes and "deal" in nodes          # finished agents were not re-run
    with urllib.request.urlopen(base + "/history", timeout=10) as r:
        assert len(json.load(r)["rows"]) > 3


def test_only_run_py_flags_are_accepted(base):
    for args in (["--rm"], ["--crash-after", "checkout"], ["--rewind", "1; ls"]):
        with pytest.raises(urllib.error.HTTPError) as err:
            post(base, "/run", {"args": args})
        assert err.value.code == 409


def test_a_malformed_body_is_a_409_not_a_crash(base):
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(urllib.request.Request(base + "/stop", data=b"not json", method="POST"), timeout=10)
    assert err.value.code == 409
