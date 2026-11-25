"""An independent small-instance oracle plus boundary and regression cases."""

import itertools
import random
import unittest
from collections import Counter

from atlas._cut_model import Piece, Stock
from atlas._cut_refine import refine
from atlas.solver import solve


def stock(i, length, kind="stock", material="oak"):
    return {"id": str(i), "material": material, "length_mm": length, "kind": kind}


def part(i, length, qty=1, material="oak"):
    return {"id": str(i), "label": str(i), "material": material, "length_mm": length, "qty": qty}


def objective(metrics):
    return metrics["fresh_bars"], metrics["loss_mm"], metrics["bars_used"]


def exhaustive_objective(stocks, parts, kerf, reuse):
    # Deliberately enumerate all labeled assignments, independently of planner code.
    pieces = [item for item in parts for _ in range(item["qty"])]
    optimum = None
    for indices in itertools.product(range(len(stocks)), repeat=len(pieces)):
        lengths = Counter()
        for piece, index in zip(pieces, indices):
            if piece["material"] != stocks[index]["material"]:
                break
            lengths[index] += piece["length_mm"] + kerf
            if lengths[index] > stocks[index]["length_mm"]:
                break
        else:
            tails = [stocks[i]["length_mm"] - length for i, length in lengths.items()]
            score = (
                sum(stocks[i]["kind"] == "stock" for i in lengths),
                kerf * len(pieces) + sum(tail for tail in tails if tail < reuse),
                len(lengths),
            )
            if optimum is None or score < optimum:
                optimum = score
    return optimum


class SolverTests(unittest.TestCase):
    def test_piece_exchange_preserves_tails_a_single_relocation_cannot(self):
        bars = [Stock("A", 15, True), Stock("B", 15, True)]
        pieces = [Piece(str(i), n, n) for i, n in enumerate((3, 3, 3, 8))]
        # The original tails are 1 and 12. A swap of 3 and 8 gives tails of 6 and 7.
        self.assertEqual(refine(bars, pieces, (0, 0, 1, 0), 5), (0, 0, 0, 1))

    def test_matches_exhaustive_oracle_and_conserves_material(self):
        rng = random.Random(20261125)
        for case in range(160):
            with self.subTest(case=case):
                stocks = [stock(i, rng.randint(5, 24), rng.choice(["stock", "remnant"]),
                                rng.choice(["ash", "ash", "oak"]))
                          for i in range(rng.randint(1, 4))]
                parts = [part(i, rng.randint(1, 12), 1, rng.choice(["ash", "ash", "oak"]))
                         for i in range(rng.randint(1, 6))]
                kerf, reuse = rng.randint(0, 2), rng.randint(1, 8)
                expected = exhaustive_objective(stocks, parts, kerf, reuse)
                result = solve(stocks, parts, kerf, reuse)
                if expected is None:
                    self.assertEqual(result["status"], "infeasible")
                    self.assertFalse(result["bars"])
                    continue
                self.assertEqual(result["status"], "optimal")
                self.assertEqual(objective(result["metrics"]), expected)
                tally = Counter()
                for bar in result["bars"]:
                    source = stocks[int(bar["stock_id"])]
                    length = bar["tail_mm"]
                    self.assertGreaterEqual(length, 0)
                    for cut in bar["cuts"]:
                        piece = parts[int(cut["part_id"])]
                        self.assertEqual(source["material"], piece["material"])
                        self.assertEqual(piece["length_mm"], cut["length_mm"])
                        tally[cut["part_id"]] += 1
                        length += cut["length_mm"] + kerf
                    self.assertEqual(length, source["length_mm"])
                self.assertEqual(tally, {p["id"]: p["qty"] for p in parts})
                m = result["metrics"]
                self.assertEqual(m["stock_mm"], m["parts_mm"] + m["loss_mm"] + m["reusable_mm"])
                if result["baseline"]:
                    self.assertLessEqual(objective(m), objective(result["baseline"]))

    def test_branches_can_find_plan_all_three_greedy_strategies_miss(self):
        stocks = [stock(0, 10, "remnant"), stock(1, 16)]
        parts = [part(0, 7), part(1, 3, 2), part(2, 4, 2)]
        for limit in (0, 1):
            limited = solve(stocks, parts, 1, 4, node_limit=limit)
            self.assertEqual(limited["status"], "unknown")
            self.assertLessEqual(limited["nodes"], limit)
        result = solve(stocks, parts, 1, 4)
        self.assertEqual(result["status"], "optimal")
        self.assertIsNone(result["baseline"])
        self.assertEqual(result["metrics"]["loss_mm"], 5)

    def test_improves_over_first_fit_and_handles_truncation(self):
        stocks = [stock(0, 15, "remnant"), stock(1, 9), stock(2, 17), stock(3, 12, "remnant")]
        parts = [part(0, 10, 2), part(1, 5, 2), part(2, 4)]
        result = solve(stocks, parts, 1, 4)
        self.assertEqual(result["baseline"]["fresh_bars"], 2)
        self.assertEqual(result["metrics"]["fresh_bars"], 1)
        limited = solve(stocks, parts, 1, 4, node_limit=0)
        self.assertEqual(limited["status"], "feasible")
        self.assertGreaterEqual(objective(limited["metrics"]), objective(result["metrics"]))

    def test_kerf_and_reuse_threshold_boundaries(self):
        self.assertEqual(solve([stock(0, 10)], [part(0, 10)], 1, 4)["status"], "infeasible")
        for tail in (0, 3, 4, 5):
            result = solve([stock(0, 11 + tail)], [part(0, 10)], 1, 4)
            self.assertEqual(result["bars"][0]["tail_mm"], tail)
            self.assertEqual(result["metrics"]["loss_mm"], 1 + (tail if tail < 4 else 0))

    def test_multi_material_additivity_and_input_order_invariance(self):
        stocks = [stock(0, 12), stock(1, 13, "remnant", "pine")]
        parts = [part(0, 3, 2), part(1, 4, 2, "pine")]
        result = solve(stocks, parts, 1, 4)
        self.assertEqual(result["metrics"]["fresh_bars"], 1)
        self.assertEqual(result, solve(stocks[::-1], parts[::-1], 1, 4))
        self.assertEqual(solve(stocks[1:], parts, 1, 4)["status"], "infeasible")

    def test_fragmentation_proves_infeasible_despite_enough_gross_length(self):
        result = solve([stock(0, 10), stock(1, 10)], [part(0, 6, 3)], 0, 3, node_limit=0)
        self.assertEqual(result["status"], "infeasible")
        self.assertIn("at most 2", result["message"])
        self.assertEqual(result["nodes"], 0)

    def test_zero_demand_and_validation(self):
        self.assertEqual(solve([], [], 0, 1)["metrics"]["stock_mm"], 0)
        for stocks, parts, kerf, reuse in [
            ([stock(0, -1)], [], 1, 1), ([stock(0, 1)] * 2, [], 1, 1),
            ([stock(0, True)], [], 1, 1), ([], [part(0, 1, 161)], 1, 1),
            ([], [part(0, 1)] * 2, 1, 1), ([], [], -1, 4), ([], [], 1, 0),
            ([stock(0, 1, "new")], [], 1, 1), ([], [part(0, 1, 0)], 1, 1),
        ]:
            with self.subTest(stocks=stocks, parts=parts, kerf=kerf, reuse=reuse):
                with self.assertRaises(ValueError):
                    solve(stocks, parts, kerf, reuse)
