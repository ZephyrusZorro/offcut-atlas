import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path

from atlas.check import check_packet, main
from atlas.proof import verify


def packet():
    stock = [{"id": "R1", "material": "Ash", "length_mm": 418, "kind": "remnant"},
             {"id": "S1", "material": "Ash", "length_mm": 403, "kind": "stock"}]
    parts = [{"id": "P1", "label": "Long rail", "material": "Ash", "length_mm": 400, "qty": 2}]
    request = {"name": "Exhibition", "parts": parts, "kerf_mm": 3, "reuse_mm": 15}
    result = {"status": "feasible", "bars": [
        {"stock_id": "R1", "cuts": [{"part_id": "P1", "length_mm": 400}], "tail_mm": 15},
        {"stock_id": "S1", "cuts": [{"part_id": "P1", "length_mm": 400}], "tail_mm": 0}],
        "metrics": {"bars_used": 2, "fresh_bars": 1, "parts_mm": 800, "stock_mm": 821,
                    "kerf_mm": 6, "loss_mm": 6, "reusable_mm": 15},
        "baseline": None, "nodes": 2, "message": "example"}
    return {"format": "offcut-atlas/1", "run_id": "test", "stocks": stock,
            "request": request, "result": result, "verification": verify(stock, parts, 3, 15, result)}


class ProofTests(unittest.TestCase):
    def setUp(self):
        self.packet = packet()

    def direct(self, p):
        req = p["request"]
        return verify(p["stocks"], req["parts"], req["kerf_mm"], req["reuse_mm"], p["result"])

    def test_exact_fit_and_threshold_equality(self):
        p = self.packet
        self.assertTrue(check_packet(p)["valid"])
        p["request"]["reuse_mm"] = 16
        p["result"]["metrics"].update(loss_mm=21, reusable_mm=0)
        self.assertTrue(self.direct(p)["valid"])

    def test_invalid_states_fail_closed(self):
        mutations = [
            ("unknown stock", lambda p: p["result"]["bars"][1].update(stock_id="missing")),
            ("twice", lambda p: p["result"]["bars"][1].update(stock_id="R1")),
            ("material", lambda p: p["stocks"][1].update(material="Oak")),
            ("unknown part", lambda p: p["result"]["bars"][1]["cuts"][0].update(part_id="bad")),
            ("length differs", lambda p: p["result"]["bars"][1]["cuts"][0].update(length_mm=399)),
            ("requires", lambda p: p["request"]["parts"][0].update(qty=3)),
            ("conservation", lambda p: p["result"]["bars"][0].update(tail_mm=12)),
            ("integer", lambda p: p["result"]["bars"][0].update(tail_mm=-1)),
            ("duplicate", lambda p: p["request"]["parts"].append(p["request"]["parts"][0])),
            ("duplicate", lambda p: p["stocks"].append(p["stocks"][0])),
            ("no assigned", lambda p: p["result"]["bars"][0].update(cuts=[])),
            ("integer", lambda p: p["result"]["metrics"].update(fresh_bars=True)),
            ("integer", lambda p: p["request"].update(kerf_mm=3.0)),
            ("integer", lambda p: p["request"].update(reuse_mm=-1)),
            ("allocation", lambda p: p["result"].update(status="infeasible")),
            ("allocation", lambda p: p["result"].update(status="unknown")),
        ]
        for partial_error, mutate in mutations:
            with self.subTest(partial_error=partial_error):
                p = deepcopy(self.packet)
                mutate(p)
                proof = self.direct(p)
                self.assertFalse(proof["valid"])
                self.assertIn(partial_error, proof["errors"][0])

    def test_a_single_wrong_total_invalidates_proof(self):
        for metric in self.packet["result"]["metrics"]:
            with self.subTest(metric=metric):
                p = deepcopy(self.packet)
                p["result"]["metrics"][metric] += 1
                self.assertFalse(self.direct(p)["valid"])

    def test_hash_stable_across_object_key_order_and_json_format(self):
        p = json.loads(json.dumps(self.packet, indent=4, sort_keys=True))
        self.assertEqual(check_packet(p)["digest"], self.packet["verification"]["digest"])

    def test_digest_catches_edits_that_preserve_feasibility(self):
        for modify in [
            lambda p: p["request"]["parts"][0].update(label="New label"),
            lambda p: p["stocks"][0].update(source_run="other"),
            lambda p: p["result"].update(nodes=99),
            lambda p: p["result"].update(status="optimal"),
        ]:
            p = deepcopy(self.packet)
            modify(p)
            self.assertTrue(self.direct(p)["valid"])
            self.assertFalse(check_packet(p)["valid"])

    def test_malformed_structures(self):
        for bad in [None, [], True, {"format": "offcut-atlas/1", "request": []}]:
            self.assertFalse(check_packet(bad)["valid"])
        for field in ["bars", "metrics"]:
            p = deepcopy(self.packet)
            p["result"][field] = "bad"
            self.assertFalse(self.direct(p)["valid"])
        for kind in [None, [], {}]:
            p = deepcopy(self.packet)
            p["stocks"][0]["kind"] = kind
            self.assertFalse(self.direct(p)["valid"])

    def test_external_reference_detects_a_fully_recomputed_edit(self):
        p = deepcopy(self.packet)
        reference = p["verification"]["digest"]
        self.assertTrue(check_packet(p, reference.upper())["valid"])
        p["request"]["parts"][0]["label"] = "Different exhibition rail"
        p["verification"] = self.direct(p)
        self.assertTrue(check_packet(p)["valid"])
        self.assertFalse(check_packet(p, reference)["valid"])

    def test_offline_command_returns_parseable_verdict_and_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            packet_path = Path(directory) / "packet.json"
            for content, expected in [(json.dumps(self.packet), 0), ("{", 1),
                                      ('{"x":1,"x":2}', 1), ("NaN", 1)]:
                packet_path.write_text(content, encoding="utf-8")
                out = io.StringIO()
                with redirect_stdout(out):
                    self.assertEqual(main([str(packet_path)]), expected)
                self.assertIs(json.loads(out.getvalue())["valid"], expected == 0)


if __name__ == "__main__":
    unittest.main()
