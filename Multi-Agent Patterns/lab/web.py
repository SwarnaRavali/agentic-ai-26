"""What the demo servers share: one page, a live event stream, and a few JSON buttons. Standard library only.

A page connects to /events and gets the current run from its start, then every new event as it happens,
so a page opened (or reloaded) mid-run catches up. Buttons POST JSON; a bad request comes back as 409.
"""
import json
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


class EventLog:
    """Every event since the server started. A page replays from the start of the current run."""

    def __init__(self):
        self.events, self.start = [], 0
        self.cond = threading.Condition()

    def add(self, ev, new_run=False):
        with self.cond:
            if new_run:
                self.start = len(self.events)
            self.events.append(ev)
            self.cond.notify_all()

    def forget(self):
        """A page that connects from now on replays nothing: the last run is no longer on screen anywhere."""
        with self.cond:
            self.start = len(self.events)


class Handler(BaseHTTPRequestHandler):
    """Serves `page` at /, the event log at /events. Subclasses add routes in get() and post()."""
    page = None          # file in web/
    log = None           # EventLog

    def hello(self):
        """The first event a page gets: whatever it needs before the run's own events."""
        return {}

    def get(self, path, query):
        return False     # True when handled

    def post(self, path, body):
        raise LookupError(path)

    def log_message(self, *args):
        pass

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path == "/":
            self.send(200, (WEB / self.page).read_bytes(), "text/html; charset=utf-8")
        elif path == "/events":
            self.events()
        elif not self.get(path, query):
            self.json({"error": "not found"}, 404)

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and origin.split("://")[-1] != self.headers.get("Host"):
            return self.json({"error": "cross-origin request"}, 403)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            self.post(self.path, body)
        except LookupError:
            return self.json({"error": "not found"}, 404)
        except (ValueError, RuntimeError) as e:
            return self.json({"error": str(e)}, 409)
        self.json({"ok": True})

    def events(self):
        """Server-sent events: the current run from its start, then everything after, live."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        log = self.log
        with log.cond:
            i = log.start
        try:
            self.sse({"type": "hello", **self.hello()})
            while True:
                with log.cond:
                    log.cond.wait_for(lambda: len(log.events) > i, timeout=15)
                    batch, i = log.events[i:], len(log.events)
                for ev in batch:
                    self.sse(ev)
                if not batch:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def sse(self, ev):
        self.wfile.write(b"data: " + json.dumps(ev, ensure_ascii=False, default=str).encode() + b"\n\n")
        self.wfile.flush()

    def json(self, obj, status=200):
        self.send(status, json.dumps(obj, ensure_ascii=False, default=str).encode(), "application/json; charset=utf-8")

    def send(self, status, data, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def in_use(port):
    """On Windows two servers can bind one port silently, so check before binding."""
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def serve(servers, url, banner, browser=True, on_exit=()):
    """Run the first server in this thread and the rest in the background until Ctrl+C."""
    for s in servers[1:]:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    print(banner + "   (Ctrl+C to stop)")
    if browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for stop in on_exit:
            stop()
        for s in servers:
            s.server_close()


def make(handler, port):
    if port and in_use(port):
        raise SystemExit(f"Port {port} is already in use by another program. Stop it, or pick another port.")
    return ThreadingHTTPServer(("127.0.0.1", port), handler)
