import random
import unittest
from copy import deepcopy
from atlas.demo import horizon_example
from atlas.horizon import lookahead, OBJECTIVE
from atlas.replay import compare_horizon
from tools.horizon_check import joint_optimum


class HorizonTests(unittest.TestCase):
    def test_joint_prevents_unnecessary_fresh_rail(self):
        stock, orders, t = horizon_example()
        before = deepcopy((stock,orders))
        pair = compare_horizon("Workshop", stock,orders,t)
        self.assertEqual(pair["sequential"]["totals"]["fresh_bars"],2)
        self.assertEqual(pair["joint"]["totals"],dict(fresh_bars=1,loss_mm=9,bars_used=3))
        self.assertTrue(all(s["verification"]["valid"] for s in pair["joint"]["stages"]))
        self.assertEqual((stock,orders),before)

    def test_joint_matches_independent_oracle(self):
        rng = random.Random(209)
        for i in range(160):
            stock,orders,_ = horizon_example()
            stock[0]["length_mm"] = rng.randrange(350,801,25)
            threshold = rng.choice([100,200,300])
            for order in orders:
                order["kerf_mm"] = rng.randint(0,6)
                for part in order["parts"]:
                    part["length_mm"] = rng.randrange(200,751,25)-order["kerf_mm"]
                    if i>70 and rng.randrange(3)==0:
                        part["material"]="Ash"
            if i>70:
                stock[1]["material"]="Ash"
                orders[0]["parts"][0]["qty"]=2
            expected = joint_optimum(stock,orders,threshold)["objective"]
            joint = lookahead(stock,orders,threshold)
            self.assertEqual(joint["status"],"optimal" if expected else "infeasible")
            if expected:
                self.assertEqual(tuple(joint["totals"][k] for k in OBJECTIVE),expected)

    def test_bounds_and_incumbent(self):
        stock,orders,t = horizon_example()
        self.assertEqual(lookahead(stock,orders,t,node_limit=0)["status"],"feasible")
        orders[1]["parts"][0]["qty"]=20
        self.assertEqual(lookahead(stock,orders,t)["status"],"too_large")
        orders[1]["parts"][0]["qty"]=1
        orders[1]["parts"][0]["material"]="Missing"
        self.assertEqual(lookahead(stock,orders,t,node_limit=0)["status"],"unknown")
