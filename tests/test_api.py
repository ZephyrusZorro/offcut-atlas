import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from atlas import demo
from atlas.ledger import Ledger
from atlas.server import Server
from atlas.worker import Worker, process_one


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.db = Ledger(Path(cls.directory.name) / "test.sqlite3")
        cls.db.initialize()
        process_one(cls.db)
        worker = Worker(cls.db)
        cls.server = Server(("127.0.0.1", 0), cls.db, worker)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(3)
        cls.server.server_close()
        cls.directory.cleanup()

    def fetch(self, path, data=None, headers=None):
        if data is not None and not isinstance(data, bytes):
            data = json.dumps(data).encode()
        request = urllib.request.Request(self.base+path, data, {"Content-Type":"application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read())

    def test_get_workspace_snapshot_and_export(self):
        code, ws = self.fetch("/api/v1/workspace")
        self.assertEqual(code, 200)
        key = next(r["id"] for r in ws["runs"] if r["status"] == "optimal")
        status, packet = self.fetch("/api/v1/runs/"+key+"/packet")
        self.assertEqual(status, 200)
        self.assertTrue(packet["verification"]["valid"])

    def test_http_input_and_origin_controls(self):
        path = "/api/v1/stock"
        item = dict(material="Black ash", kind="stock", length_mm=1000, qty=1)
        for body, hdrs, expected in [(b"{}", {"Content-Type":"text/plain"}, 415),
                (item, {"Origin":"https://example.org"}, 403), (item, {"Host":"example.org"}, 403),
                (b"{}",{},422), (b'{"qty":1,"qty":2}',{},400), (b"["*2000,{},400),
                (b"x"*70000,{},413), (b'{"qty":NaN}',{},400)]:
            with self.subTest(expected=expected):
                self.assertEqual(self.fetch(path, body, hdrs)[0], expected)

    def test_queue_and_retry_via_http(self):
        order = dict(demo.ORDER, name="Retry acceptance")
        a = self.fetch("/api/v1/runs", order, {"Idempotency-Key":"a-run"})
        b = self.fetch("/api/v1/runs", order, {"Idempotency-Key":"a-run"})
        self.assertEqual(a, b)
        self.assertEqual(a[0], 202)

    def test_joint_endpoints_use_real_search_and_leave_inventory_unchanged(self):
        before = self.db.workspace()
        code, example = self.fetch("/api/v1/experiments/lookahead")
        self.assertEqual(code, 200)
        self.assertEqual(example["joint"]["totals"]["fresh_bars"], 1)
        key = next(r["id"] for r in before["runs"] if r["status"] == "optimal")
        code, evaluated = self.fetch("/api/v1/runs/"+key+"/lookahead",
                                     {"threshold_mm": 250, "next_order": demo.ORDER})
        self.assertEqual(code, 200)
        self.assertEqual(evaluated["joint"]["status"], "too_large")
        self.assertEqual(before, self.db.workspace())

    def test_intake_retry_via_http(self):
        item = dict(material="White ash", kind="stock", length_mm=2400, qty=2)
        a = self.fetch("/api/v1/stock", item, {"Idempotency-Key":"dock-ticket"})
        b = self.fetch("/api/v1/stock", item, {"Idempotency-Key":"dock-ticket"})
        self.assertEqual(a,b)
        self.assertEqual(self.fetch("/api/v1/stock", dict(item, qty=1), {"Idempotency-Key":"dock-ticket"})[0],409)
