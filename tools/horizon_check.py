"""Small exact two-order reference for checking the consequences of myopic planning."""

import argparse
import itertools
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def counterexample():
    rack = [{"id": key, "material": "Maple", "length_mm": length, "kind": kind}
            for key, length, kind in (("R", 700, "remnant"), ("A", 1000, "stock"),
                                      ("B", 1000, "stock"))]
    orders = []
    for name, lengths in (("Study", [397]), ("Exhibition", [697, 597])):
        parts = [dict(id=f"P{i}", label=f"Frame rail {i}", length_mm=length,
                      material="Maple", qty=1) for i, length in enumerate(lengths, 1)]
        orders.append(dict(name=name, parts=parts, kerf_mm=3, reuse_mm=200))
    return rack, orders, 200


def assignments(rack, order, threshold):
    """Enumerate every map from ordered physical pieces to eligible rail lineages."""
    pieces = [part for part in order["parts"] for _ in range(part["qty"])]
    eligible = [[i for i, rail in enumerate(rack) if rail["material"] == part["material"]]
                for part in pieces]
    for mapping in itertools.product(*eligible):
        cuts = [[] for _ in rack]
        for rail_index, part in zip(mapping, pieces, strict=True):
            cuts[rail_index].append(part)
        next_rack, witness = [], []
        fresh = loss = opened = 0
        for rail, group in zip(rack, cuts, strict=True):
            if not group:
                next_rack.append(rail)
                continue
            kerf = order["kerf_mm"] * len(group)
            tail = rail["length_mm"] - kerf - sum(p["length_mm"] for p in group)
            if tail < 0:
                break
            fresh += int(rail["kind"] == "stock")
            opened += 1
            loss += kerf
            if tail >= threshold:
                # One retained tail per parent. The lineage ID stays unique across periods.
                next_rack.append({**rail, "length_mm": tail, "kind": "remnant"})
            else:
                loss += tail
            witness.append({"lineage": rail["id"], "input_mm": rail["length_mm"],
                            "parts_mm": [p["length_mm"] for p in group], "tail_mm": tail})
        else:
            yield (fresh, loss, opened), next_rack, witness


def joint_optimum(rack, orders, threshold):
    """Enumerate both periods together under the real rack, material and retention rules."""
    if len(orders) != 2 or len(rack) > 5:
        raise ValueError("This reference supports two orders and at most five rails.")
    quantity = sum(part["qty"] for order in orders for part in order["parts"])
    if quantity > 6:
        raise ValueError("The exhaustive reference accepts at most six pieces in total.")
    best_score, best_witness, completed = None, None, 0
    first_count = 0
    for first, carried, first_plan in assignments(rack, orders[0], threshold):
        first_count += 1
        for second, _, second_plan in assignments(carried, orders[1], threshold):
            completed += 1
            score = tuple(x + y for x, y in zip(first, second, strict=True))
            if best_score is None or score < best_score:
                best_score = score
                best_witness = [first_plan, second_plan]
    return {"objective": best_score, "allocation": best_witness,
            "feasible_first_assignments": first_count, "complete_pairs": completed}


def sequential_score(rack, orders, threshold):
    from atlas.replay import project

    policy = project(rack, orders, threshold)
    if not policy["complete"]:
        return None
    total = policy["totals"]
    return (total["fresh_bars"], total["loss_mm"],
            sum(s["metrics"]["bars_used"] for s in policy["stages"]))


def corpus_report():
    rng = random.Random(209)
    counts = {"cases": 48, "same_score": 0, "joint_improved": 0,
              "joint_only_complete": 0, "both_unfillable": 0}
    for _ in range(counts["cases"]):
        rack, orders, _ = counterexample()
        rack[0]["length_mm"] = rng.randrange(350, 801, 25)
        threshold = rng.choice([100, 200, 300])
        for order in orders:
            for part in order["parts"]:
                part["length_mm"] = rng.randrange(200, 751, 25) - order["kerf_mm"]
        sequential = sequential_score(rack, orders, threshold)
        exact = joint_optimum(rack, orders, threshold)["objective"]
        if sequential is None:
            counts["both_unfillable" if exact is None else "joint_only_complete"] += 1
        elif exact is None or exact > sequential:
            raise RuntimeError("The exact reference missed a feasible sequential witness.")
        elif exact == sequential:
            counts["same_score"] += 1
        else:
            counts["joint_improved"] += 1
    return {"seed": 209, **counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", action="store_true", help="compare 48 small seeded jobs")
    if parser.parse_args().corpus:
        print(json.dumps(corpus_report(), indent=2))
        return
    rack, orders, threshold = counterexample()
    print(json.dumps({"threshold_mm": threshold, "sequential_objective": sequential_score(rack, orders, threshold),
                      "joint_reference": joint_optimum(rack, orders, threshold)}, indent=2))


if __name__ == "__main__":
    main()
