"""Per-run trace files, so you can follow the flow end to end after the demo.

Every run writes to output/<timestamp>_<label>/ (label: safe, no-owner, resume, rewind3, ...):
  console.log   what the terminal showed
  e2e.log       one line per event: run start, trigger, LLM call, node update, interrupt, resume, end
  diff.log      the graph state before and after each node, as a unified diff
  summary.json  final state and outcome
"""
import difflib
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = Path(os.getenv("LAB_OUTPUT") or ROOT / "output")   # the tests point this at a temp folder

current = None   # the active Run, if any; lab modules call event() without importing run.py
listeners = []   # other subscribers: the live demo streams every model call to its Run log
KEEP_RUNS = 20   # run folders kept in output/; older ones are deleted when a new run starts


def _json(obj, indent=None):
    return json.dumps(obj, indent=indent, ensure_ascii=False, sort_keys=True, default=str)


def event(kind, **data):
    if current:
        current.event(kind, **data)
    for fn in list(listeners):
        fn(kind, data)


def prune(folder, pattern, keep):
    """Keep the newest `keep` entries matching `pattern` in `folder` (by name, which starts with a timestamp)."""
    import shutil
    if not folder.exists():
        return
    for old in sorted(folder.glob(pattern), key=lambda p: p.name, reverse=True)[keep:]:
        shutil.rmtree(old, ignore_errors=True) if old.is_dir() else old.unlink(missing_ok=True)


class Run:
    def __init__(self, label, options):
        prune(OUTPUT, "20[0-9][0-9]-*_*", KEEP_RUNS - 1)
        base = f"{datetime.now():%Y-%m-%d_%H-%M-%S}_{label}"
        self.dir, n = OUTPUT / base, 1
        while self.dir.exists():   # two runs in the same second: don't overwrite
            n += 1
            self.dir = OUTPUT / f"{base}-{n}"
        self.dir.mkdir(parents=True)
        self.e2e = open(self.dir / "e2e.log", "w", encoding="utf-8")
        self.diffs = open(self.dir / "diff.log", "w", encoding="utf-8")
        self.start = time.perf_counter()
        self.seq = 0
        self.prev = {}
        self.lock = threading.Lock()   # the parallel scouts log from separate threads
        global current
        current = self
        self.event("run_start", label=label, options=options)

    def event(self, kind, **data):
        t = time.perf_counter() - self.start
        line = f"{datetime.now():%H:%M:%S.%f}"[:-3] + f"  +{t:7.3f}s  {kind:<12} {_json(data)}\n"
        with self.lock:
            self.e2e.write(line)
            self.e2e.flush()

    def state(self, node, values):
        """Record the full state after `node` ran, as a diff against the state before it."""
        self.seq += 1
        before = _json(self.prev, indent=2).splitlines()
        after = _json(values, indent=2).splitlines()
        lines = difflib.unified_diff(before, after, f"before {node}", f"after {node}", lineterm="")
        self.diffs.write(f"=== #{self.seq} {node} ===\n" + ("\n".join(lines) or "(no change)") + "\n\n")
        self.diffs.flush()
        self.prev = values

    def close(self, console, state, ended=None):
        global current
        self.event("run_end", outcome=ended or state.get("outcome"), turns=state.get("turn", 0),
                   tokens=state.get("tokens", 0), cart=len(state.get("cart", [])))
        (self.dir / "summary.json").write_text(_json({"ended": ended, "state": state}, indent=2) + "\n",
                                               encoding="utf-8")
        (self.dir / "console.log").write_text(console.export_text(), encoding="utf-8")
        self.e2e.close()
        self.diffs.close()
        current = None
        console.print(f"[dim]{'':>9} Logs: {self.dir.relative_to(ROOT) if self.dir.is_relative_to(ROOT) else self.dir}[/]")
