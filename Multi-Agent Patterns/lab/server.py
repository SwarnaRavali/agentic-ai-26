"""The guardrails lab in the browser: watch the shoe team run, switch guardrails, crash, resume, rewind.

  python -m lab.server              opens http://127.0.0.1:8702

The page does not run the graph itself. Each button starts run.py as a subprocess, with the same flags as
the terminal, and the server streams that run's trace (output/<run>/e2e.log and diff.log) to the page as
it is written. So "crash" really kills a process, and the approval is typed into run.py's stdin.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time

from lab import claude_cli, feed, guards, llm, trace, web

ROOT = web.WEB.parent
PORT = 8702
CRASH_NODES = ["watcher", "scout", "evaluator", "deal", "budget"]
FLAGS = {"--no-owner", "--no-budget", "--no-approval", "--unsafe", "--chaos", "--watch", "--resume"}
E2E_LINE = re.compile(r"^(\S+)\s+\+\s*([\d.]+)s\s+(\S+)\s+(\{.*\})$")   # see trace.Run.event
DIFF_SECTION = re.compile(r"=== #(\d+) (.+?) ===\n(.*?)\n\n", re.S)       # see trace.Run.state


def check_args(args):
    """Only run.py flags the page offers; the page never sends free text to a command line."""
    out, i = [], 0
    while i < len(args):
        a, nxt = str(args[i]), str(args[i + 1]) if i + 1 < len(args) else None
        if a in FLAGS:
            out.append(a)
        elif a == "--crash-after" and nxt in CRASH_NODES or a == "--rewind" and nxt and nxt.isdigit():
            out += [a, nxt]
            i += 1
        else:
            raise ValueError(f"not allowed: {a!r}")
        i += 1
    return out


class Session:
    """The current run.py process. One run at a time."""

    def __init__(self):
        self.log = web.EventLog()
        self.proc = None
        self.feed = None

    def emit(self, type_, **data):
        self.log.add({"type": type_, **data}, new_run=type_ == "start")

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def launch(self, args, delay, brain=None):
        with self.log.cond:
            if self.running():
                raise RuntimeError("A run is already in progress. Stop it first.")
            before = _run_dirs()
            env = {**os.environ, "LAB_DELAY": str(delay), "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1",
                   "COLUMNS": "110"}
            if brain:                       # the page's Brain picker: run.py reads the model from its environment
                if brain not in llm.BRAINS:
                    raise ValueError("unknown brain")
                if brain != "offline" and not claude_cli.available():
                    raise RuntimeError("The claude CLI was not found. Install Claude Code, or set CLAUDE_BIN.")
                env["LAB_LLM"], env["LAB_MODEL"] = llm.BRAINS[brain]
            self.proc = subprocess.Popen([sys.executable, "run.py", *args], cwd=ROOT, env=env, text=True,
                                         encoding="utf-8", errors="replace", stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.emit("start", args=args, delay=delay, mode=env.get("LAB_LLM", "offline"), model=env.get("LAB_MODEL", ""))
        threading.Thread(target=self._console, args=(self.proc,), daemon=True).start()
        threading.Thread(target=self._tail, args=(self.proc, before), daemon=True).start()

    def answer(self, reply):
        """Guardrail 3 from the browser: run.py is waiting at its approval prompt, on stdin."""
        if reply not in ("approve", "deny"):
            raise ValueError("answer must be approve or deny")
        if not self.running():
            raise RuntimeError("No run is waiting for an answer.")
        self.proc.stdin.write(reply + "\n")
        self.proc.stdin.flush()
        self.emit("answered", answer=reply)

    def stop(self):
        if self.running():
            self.emit("stopping")
            self.proc.terminate()

    def _console(self, proc):
        for line in proc.stdout:
            self.emit("console", text=line.rstrip("\n"))

    def _tail(self, proc, before):
        """Follow the new run's log files until run.py exits. A crash or kill leaves them complete up to there."""
        run_dir, lines, diffs = None, 0, 0
        while True:
            alive = proc.poll() is None      # read before the files, so the last pass sees everything
            if run_dir is None:
                new = _run_dirs() - before
                if new:
                    run_dir = max(new, key=lambda d: d.stat().st_mtime)
                    self.emit("run_dir", name=run_dir.name)
            if run_dir:
                lines = self._e2e(run_dir / "e2e.log", lines)
                diffs = self._diffs(run_dir / "diff.log", diffs)
            if not alive:
                break
            time.sleep(0.1)
        summary = None
        if run_dir and (run_dir / "summary.json").exists():
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        self.emit("exit", code=proc.returncode, summary=summary)

    def _e2e(self, path, done):
        if not path.exists():
            return done
        complete = path.read_text(encoding="utf-8", errors="replace").split("\n")[:-1]   # skip a half-written line
        for line in complete[done:]:
            m = E2E_LINE.match(line)
            if m:
                self.emit("e2e", kind=m[3], t=float(m[2]), data=json.loads(m[4]))
        return len(complete)

    def _diffs(self, path, done):
        if not path.exists():
            return done
        sections = DIFF_SECTION.findall(path.read_text(encoding="utf-8", errors="replace"))
        for seq, name, body in sections[done:]:
            self.emit("diff", seq=int(seq), name=name, body=body)
        return len(sections)

    def watch_feed(self):
        """The price feed is the agents' world; the page shows every change, whoever made it."""
        while True:
            try:
                items = feed.read_feed(retries=3)
            except RuntimeError:
                items = self.feed
            if items != self.feed:
                self.feed = items
                self.emit("feed", items=items)
            time.sleep(0.25)


SESSION = Session()


def _run_dirs():
    return {d for d in trace.OUTPUT.glob("*") if d.is_dir()} if trace.OUTPUT.exists() else set()


def history_rows():
    from lab import runner   # imported here: it loads lab.llm, which checks the model settings
    return [{"n": n, "next": list(s.next), "turn": s.values.get("turn", 0), "tokens": s.values.get("tokens", 0),
             "owner": s.values.get("owner"), "cart": len(s.values.get("cart", []))}
            for n, s in runner.history(show=False)]


class Handler(web.Handler):
    page = "lab.html"
    log = SESSION.log

    def hello(self):
        return {"goal": feed.GOAL, "max_turns": guards.MAX_TURNS, "max_tokens": guards.MAX_TOKENS,
                "crash_nodes": CRASH_NODES, "mode": os.getenv("LAB_LLM", "offline"), "model": os.getenv("LAB_MODEL", ""),
                "claude": claude_cli.available(),
                "feed": SESSION.feed, "running": SESSION.running()}

    def get(self, path, query):
        if path != "/history":
            return False
        if SESSION.running():
            self.json({"error": "Checkpoints are listed when the run ends."}, 409)
        else:
            try:
                self.json({"rows": history_rows()})
            except BaseException as e:   # no earlier run (SystemExit), bad model settings, ...
                self.json({"error": str(e) or type(e).__name__}, 404)
        return True

    def post(self, path, body):
        if path == "/run":
            SESSION.launch(check_args(body.get("args", [])), min(max(float(body.get("delay", 0.7)), 0), 3),
                           body.get("brain"))
        elif path == "/answer":
            SESSION.answer(body.get("answer"))
        elif path == "/stop":
            SESSION.stop()
        elif path == "/drop":
            feed.drop_price()
        else:
            raise LookupError(path)


_feed_thread = None


def make_server(port=PORT):
    global _feed_thread
    if _feed_thread is None:
        _feed_thread = threading.Thread(target=SESSION.watch_feed, daemon=True)
        _feed_thread.start()
    return web.make(Handler, port)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    a = p.parse_args()
    url = f"http://127.0.0.1:{a.port}"
    web.serve([make_server(a.port)], url, f"Guardrails lab: {url}", not a.no_browser, [SESSION.stop])


if __name__ == "__main__":
    main()
