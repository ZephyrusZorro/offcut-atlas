import copy
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from atlas import demo
from atlas.check import check_packet
from atlas.ledger import Ledger
from atlas.validation import Problem
from atlas.worker import process_one


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Ledger(Path(self.directory.name) / "studio.sqlite")
        self.db.initialize()
        self.first = self.db.workspace()["runs"][0]["id"]

    def test_duplicate_submission_and_payload_binding(self):
        with ThreadPoolExecutor(6) as pool:
            ids = list(pool.map(lambda _: self.db.submit(demo.ORDER, "one"), range(10)))
        self.assertEqual(len(set(ids)), 1)
        with self.assertRaisesRegex(Problem, "different order"):
            self.db.submit(dict(demo.ORDER, name="Another"), "one")
        self.assertEqual(len(self.db.workspace()["runs"]), 2)

    def test_intake_retry_is_bound_to_payload_and_single_revision(self):
        before = self.db.workspace()
        item = dict(material="Black ash", kind="stock", length_mm=1000, qty=2)
        with ThreadPoolExecutor(4) as pool:
            receipts = list(pool.map(lambda _: self.db.add_stock(item, "intake-1"), range(8)))
        self.assertTrue(all(r == receipts[0] for r in receipts))
        self.assertEqual(len(self.db.workspace()["stocks"]), len(before["stocks"])+2)
        self.assertEqual(self.db.workspace()["revision"], before["revision"]+1)
        with self.assertRaisesRegex(Problem, "different stock receipt"):
            self.db.add_stock(dict(item, qty=3), "intake-1")

    def test_racing_bookings_and_idempotent_receipt(self):
        second = self.db.submit(dict(demo.ORDER, name="Another booking"))
        for _ in range(2):
            self.assertTrue(process_one(self.db))
        def book(key):
            try:
                return self.db.commit(key)
            except Problem as exc:
                return exc.code
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(book, (self.first, second)))
        self.assertIn("stock_conflict", results)
        receipt = next(r for r in results if isinstance(r, dict))
        self.assertEqual(receipt, self.db.commit(receipt["run_id"]))
        self.assertEqual(self.db.workspace()["revision"], 2)
        self.assertGreater(len(receipt["returned"]), 0)
        stock = self.db.workspace()["stocks"]
        for tail in receipt["returned"]:
            row = next(s for s in stock if s["id"] == tail["id"])
            self.assertEqual((row["parent_id"], row["source_run"]), (tail["parent_id"], receipt["run_id"]))
        self.assertTrue(check_packet(self.db.packet(receipt["run_id"]))["valid"])

    def test_rollback_after_partial_booking(self):
        process_one(self.db)
        run = self.db.run(self.first)
        # An injected storage fault on the second update exercises rollback of the first return.
        second_id = run["result"]["bars"][1]["stock_id"]
        with self.db.transaction(write=True) as db:
            db.execute("""CREATE TRIGGER fail_booking BEFORE UPDATE OF consumed_by ON rails
                       WHEN OLD.id='""" + second_id + """' BEGIN SELECT RAISE(ABORT, 'test fault'); END""")
        before = self.db.workspace()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.commit(self.first)
        self.assertEqual(self.db.workspace(), before)
        self.assertFalse(self.db.run(self.first)["committed"])

    def test_late_worker_cannot_finish_reclaimed_job(self):
        run_id, old, *_ = self.db.claim()
        with self.db.transaction(write=True) as db:
            db.execute("UPDATE runs SET lease_until=0 WHERE id=?", (run_id,))
        reopened = Ledger(self.db.path)
        self.assertEqual(reopened.claim()[0], run_id)
        self.assertFalse(self.db.finish(run_id, old, "failed", error="Stale worker"))
        self.assertEqual(reopened.run(run_id)["status"], "running")

    def test_four_interrupted_claims_become_inspectable_failure(self):
        for _ in range(4):
            self.assertIsNotNone(self.db.claim())
            with self.db.transaction(write=True) as db:
                db.execute("UPDATE runs SET lease_until=0")
        self.assertIsNone(self.db.claim())
        self.assertEqual(self.db.run(self.first)["status"], "failed")
        self.assertEqual(len(self.db.workspace()["stocks"]), 9)

    def test_verification_failure_cannot_change_stock(self):
        with patch("atlas.worker.verify", return_value={"valid": False, "digest": "", "errors": ["test"]}):
            self.assertTrue(process_one(self.db))
        self.assertEqual(self.db.run(self.first)["status"], "failed")
        with self.assertRaises(Problem):
            self.db.commit(self.first)
        with self.assertRaises(Problem):
            self.db.packet(self.first)
        self.assertEqual(self.db.workspace()["revision"], 1)

    def test_malformed_requests_leave_no_state(self):
        before = self.db.workspace()
        for field, value in (("kerf_mm", True), ("reuse_mm", -1), ("name", "\x00"), ("parts", [])):
            with self.subTest(field=field), self.assertRaises(Problem):
                self.db.submit(dict(demo.ORDER, **{field: value}))
        duplicate = copy.deepcopy(demo.ORDER)
        duplicate["parts"].append(duplicate["parts"][0])
        with self.assertRaises(Problem):
            self.db.submit(duplicate)
        self.assertEqual(self.db.workspace(), before)

    def test_unicode_material_equivalence_preserves_old_inventory(self):
        with self.db.transaction(write=True) as db:
            db.execute("INSERT INTO rails(id,material,length_mm,kind) VALUES(?,?,?,?)",
                       ("historical", "Che\u0302ne", 1000, "stock"))
        order = dict(demo.ORDER, parts=[dict(demo.ORDER["parts"][0], material="Chêne", qty=1)])
        key = self.db.submit(order)
        while process_one(self.db):
            pass
        self.assertEqual(self.db.run(key)["result"]["bars"][0]["stock_id"], "historical")

    def test_offline_backup_reopens_and_preserves_proof(self):
        process_one(self.db)
        self.db.commit(self.first)
        path = self.db.path.with_name("backup.sqlite")
        command = [sys.executable, "-m", "atlas", "backup", str(path), "--db", str(self.db.path)]
        subprocess.run(command, capture_output=True, check=True)
        self.assertEqual(self.db.workspace(), Ledger(path).workspace())
        self.assertTrue(check_packet(Ledger(path).packet(self.first))["valid"])
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)

    def test_v1_upgrade_preserves_saved_jobs(self):
        with self.db.transaction(write=True) as db:
            db.execute("DROP TABLE intakes")
            db.execute("PRAGMA user_version=1")
        before = self.db.workspace()
        self.db.initialize()
        self.assertEqual(self.db.workspace(), before)
        with self.db.transaction() as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_snapshot_survives_new_stock_and_tamper_rejected(self):
        self.db.add_stock(dict(material="Natural oak", kind="stock", length_mm=8000, qty=1))
        process_one(self.db)
        run = self.db.run(self.first)
        self.assertEqual(len(run["stocks"]), 9)
        result = run["result"]
        result["bars"][0]["tail_mm"] += 1
        with self.db.transaction(write=True) as db:
            db.execute("UPDATE runs SET result=? WHERE id=?", (json.dumps(result),self.first))
        with self.assertRaisesRegex(Problem, "verification"):
            self.db.commit(self.first)
