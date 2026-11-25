"""Bounded local HTTP adapter. Static files are served from an explicit manifest."""
import json
import logging
import re
import socket
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .demo import horizon_example
from .replay import compare_horizon, lookahead_run, scenario
from .validation import Problem, fields

LOG = logging.getLogger("atlas.http")
ASSETS = Path(__file__).with_name("static")
TYPES = {".html": "text/html", ".js": "application/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".ico":"image/x-icon"}
RUN_PATH = re.compile(r"/api/v1/runs/(run-[0-9a-f]{32})(?:/(packet|commit|replay|lookahead))?")
CSP = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'self'"


def unique_keys(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("Duplicate JSON key")
        data[key] = value
    return data


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, ledger, worker):
        self.ledger, self.worker = ledger, worker
        self.replay_slot = threading.BoundedSemaphore(1)
        self.clients = threading.BoundedSemaphore(24)
        super().__init__(address, Handler)
        port = self.server_port
        self.authorities = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            self.authorities.update(("127.0.0.1", "localhost"))
        self.assets = {"/static/"+p.name: p for p in ASSETS.iterdir() if p.is_file() and p.suffix in TYPES}
        self.assets.update({"/": ASSETS/"index.html", "/lab.html": ASSETS/"lab.html",
                            "/sheet.html": ASSETS/"sheet.html"})

    def process_request(self, request, client_address):
        if not self.clients.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.clients.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.clients.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "OffcutAtlas/1"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(8)

    def log_message(self, fmt, *args):
        # Avoid logging user-supplied paths, headers and labels.
        pass

    def reply(self, status, payload, kind="application/json", headers=None):
        body = (json.dumps(payload, ensure_ascii=False, allow_nan=False).encode() if kind == "application/json" else payload)
        self.send_response(status)
        self.send_header("Content-Type", kind+"; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        try:
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except (ConnectionError, TimeoutError):
            self.close_connection = True

    def body(self):
        if self.headers.get_content_type() != "application/json":
            raise Problem(415, "body_type", "Send a JSON object with Content-Type application/json.")
        size = self.headers.get_all("Content-Length", [])
        if len(size) != 1 or not re.fullmatch(r"[0-9]{1,8}", size[0]) or self.headers.get("Transfer-Encoding"):
            raise Problem(400, "body_size", "Send one content length and an unchunked request.")
        length = int(size[0])
        if length > 64 * 1024:
            raise Problem(413, "body_large", "JSON body exceeds 64 KiB.")
        try:
            raw = self.rfile.read(length)
            self.body_consumed = True
            if len(raw) != length:
                raise ValueError("Incomplete body")
            return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_keys,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid numeric constant")))
        except (ValueError, RecursionError):
            raise Problem(400, "invalid_json", "Send well-formed UTF-8 JSON with unique keys.") from None

    def dispatch(self):
        host = self.headers.get_all("Host", [])
        if len(host) != 1 or host[0].lower() not in self.server.authorities:
            raise Problem(403, "host", "Use this service through its loopback address.")
        if self.command == "POST":
            origins = self.headers.get_all("Origin", [])
            if (origins and origins != ["http://"+host[0]]) or self.headers.get("Sec-Fetch-Site") == "cross-site":
                raise Problem(403, "origin", "Only same-origin browser writes are accepted.")
        path = urlsplit(self.path).path
        ledger = self.server.ledger
        match = RUN_PATH.fullmatch(path)
        if self.command in ("GET", "HEAD"):
            if path in self.server.assets:
                file = self.server.assets[path]
                return self.reply(200, file.read_bytes(), TYPES[file.suffix])
            if path == "/api/v1/health":
                with ledger.transaction() as db:
                    version = db.execute("PRAGMA user_version").fetchone()[0]
                return self.reply(200, dict(status="ok", schema=version, worker=self.server.worker.is_alive()))
            if path == "/api/v1/workspace":
                return self.reply(200, ledger.workspace())
            if path == "/api/v1/experiments/lookahead":
                return self.reply(200, compare_horizon("Maple teaching case", *horizon_example()))
            if match and match[2] is None:
                return self.reply(200, ledger.run(match[1]))
            if match and match[2] == "packet":
                return self.reply(200, ledger.packet(match[1]), headers={"Content-Disposition":
                                  f'attachment; filename="offcut-{match[1]}.json"'})
        elif self.command == "POST":
            data = self.body()
            key = self.headers.get("Idempotency-Key")
            if key is not None and not re.fullmatch(r"[A-Za-z0-9_.-]{1,96}", key):
                raise Problem(422, "key_format", "Invalid Idempotency-Key.")
            if path == "/api/v1/runs":
                run_id = ledger.submit(data, key)
                self.server.worker.wake.set()
                return self.reply(202, {"id": run_id}, headers={"Location": f"/api/v1/runs/{run_id}"})
            if path == "/api/v1/stock":
                return self.reply(201, ledger.add_stock(data, key))
            if match and match[2] == "commit":
                fields(data, ())
                return self.reply(200, ledger.commit(match[1]))
            if match and match[2] in ("replay", "lookahead"):
                if not self.server.replay_slot.acquire(blocking=False):
                    raise Problem(429, "replay_busy", "Another two-order replay is running. Try again shortly.")
                try:
                    experiment = scenario if match[2] == "replay" else lookahead_run
                    return self.reply(200, experiment(ledger.run(match[1]), data))
                finally:
                    self.server.replay_slot.release()
        raise Problem(404, "not_found", "Resource not found.")

    def reject(self, exc):
        self.reply(exc.status, {"error": str(exc), "code": exc.code})
        if self.command != "POST" or getattr(self, "body_consumed", False):
            return
        # Windows can reset a connection closed with unread request bytes, masking
        # the response. Send FIN first, then briefly drain bounded outstanding data.
        try:
            self.connection.shutdown(socket.SHUT_WR)
            self.connection.settimeout(0.15)
            deadline = time.monotonic() + 0.20
            remaining = 128 * 1024
            while remaining and time.monotonic() < deadline:
                chunk = self.rfile.read1(min(remaining, 8192))
                if not chunk:
                    break
                remaining -= len(chunk)
        except OSError:
            pass

    def handle_method(self):
        try:
            self.dispatch()
        except Problem as exc:
            self.reject(exc)
        except (ConnectionError, TimeoutError):
            self.close_connection = True
        except sqlite3.OperationalError:
            LOG.exception("storage_unavailable")
            self.reply(503, {"error": "Ledger temporarily unavailable. Retry the request.", "code": "ledger_busy"})
        except Exception:
            LOG.exception("request_failed")
            self.reply(500, {"error": "The request could not be completed.", "code": "internal"})

    do_GET = do_HEAD = do_POST = handle_method
