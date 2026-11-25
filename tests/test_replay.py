import unittest
from copy import deepcopy

from atlas.replay import scenario
from tools.horizon_check import counterexample, joint_optimum


def boundary_fixture(rail_count=2):
    stocks = [{"id": f"A{i}", "material": "Ash", "length_mm": 1000, "kind": "stock"}
              for i in range(rail_count)]
    def order(name, length):
        return {"name": name, "kerf_mm": 3, "reuse_mm": 300, "parts": [
            {"id": "P", "label": "Frame", "material": "Ash", "length_mm": length, "qty": 1}]}
    run = {"id": "sample", "revision": 3, "stocks": stocks, "request": order("Initial", 797)}
    body = {"threshold_a": 200, "threshold_b": 201, "next_order": order("Following", 197)}
    return run, body


class ReplayTests(unittest.TestCase):
    def test_two_orders_match_hand_calculated_threshold_boundary(self):
        run, body = boundary_fixture()
        retained, discarded = scenario(run, body)["policies"]
        self.assertTrue(retained["complete"] and discarded["complete"])
        self.assertEqual(retained["totals"], {"fresh_bars": 1, "loss_mm": 6, "parts_mm": 994})
        self.assertEqual(discarded["totals"], {"fresh_bars": 2, "loss_mm": 206, "parts_mm": 994})
        self.assertEqual(retained["stages"][0]["returned"],
                         [{"parent_id": "A0", "length_mm": 200, "material": "Ash"}])
        self.assertEqual(discarded["stages"][0]["returned"], [])
        first, second = retained["stages"]
        self.assertEqual(first["metrics"]["stock_mm"], 1000)
        self.assertEqual(second["metrics"]["stock_mm"], 200)
        self.assertEqual(second["metrics"]["fresh_bars"], 0)
        self.assertEqual(discarded["stages"][1]["metrics"]["stock_mm"], 1000)
        self.assertEqual(retained["ending_rails"], 1)
        self.assertEqual(discarded["ending_rails"], 1)

    def test_policy_order_and_repeated_calls_leave_snapshots_independent(self):
        run, body = boundary_fixture()
        saved = deepcopy((run, body))
        first = scenario(run, body)["policies"]
        reverse = scenario(run, {**body, "threshold_a": 201, "threshold_b": 200})["policies"]
        repeated = scenario(run, body)["policies"]
        self.assertEqual(first, list(reversed(reverse)))
        self.assertEqual(first, repeated)
        self.assertEqual((run, body), saved)

    def test_second_period_shortage_has_no_completed_aggregate(self):
        run, body = boundary_fixture(rail_count=1)
        retained, discarded = scenario(run, body)["policies"]
        self.assertTrue(retained["complete"])
        self.assertFalse(discarded["complete"])
        self.assertIsNone(discarded["totals"])
        self.assertEqual([s["status"] for s in discarded["stages"]], ["optimal", "infeasible"])
        self.assertNotIn("digest", discarded["stages"][1])

    def test_exact_horizon_can_outperform_two_individually_optimal_orders(self):
        stocks, orders, threshold = counterexample()
        run = {"id": "example", "revision": 0, "stocks": stocks, "request": orders[0]}
        body = {"threshold_a": threshold, "threshold_b": threshold+1, "next_order": orders[1]}
        sequential = scenario(run, body)["policies"][0]
        self.assertEqual([s["status"] for s in sequential["stages"]], ["optimal", "optimal"])
        self.assertEqual(sequential["totals"], {"fresh_bars": 2, "loss_mm": 9, "parts_mm": 1691})
        joint = joint_optimum(stocks, orders, threshold)
        self.assertEqual(joint["objective"], (1, 9, 3))
        self.assertEqual(joint["feasible_first_assignments"], 3)
        self.assertGreater(joint["complete_pairs"], 0)
        self.assertEqual(joint["allocation"][0][0]["tail_mm"], 600)

    def test_oracle_rejects_mixed_material_substitution_and_discards_scrap(self):
        run, body = boundary_fixture(rail_count=1)
        orders = [run["request"], body["next_order"]]
        self.assertIsNone(joint_optimum(run["stocks"], orders, 201)["objective"])
        self.assertEqual(joint_optimum(run["stocks"], orders, 200)["objective"], (1, 6, 2))
        orders[1]["parts"][0]["material"] = "Maple"
        self.assertIsNone(joint_optimum(run["stocks"], orders, 200)["objective"])


if __name__ == "__main__":
    unittest.main()
