"""Measure a bounded solver against an independently implemented workshop rule."""

import argparse
import json
import platform
import random
import statistics
import sys
from collections import Counter
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atlas.proof import verify
from atlas.solver import solve


def stock(i, material, length, kind="stock"):
    return {"id": f"B{i}", "material": material, "length_mm": length, "kind": kind}


def demand(i, material, length, qty=1):
    return {"id": f"P{i}", "label": f"Rail {i}", "material": material,
            "length_mm": length, "qty": qty}


def fixtures(seed):
    rng = random.Random(seed)
    tricky = [597, 497, 297, 197, 197, 197]
    yield ("packing-counterexample", [stock(i, "oak", 1000) for i in range(3)],
           [demand(i, "oak", length) for i, length in enumerate(tricky)], 3, 125)
    for i in range(12):
        bars, parts = [], []
        for material in ("oak", "ash"):
            for _ in range(2):
                bars.append(stock(len(bars), material, rng.randrange(350, 1000), "remnant"))
            for _ in range(4):
                bars.append(stock(len(bars), material, 2400))
            for _ in range(4):
                parts.append(demand(len(parts), material, rng.randrange(200, 760), rng.randint(1, 2)))
        yield f"mixed-{i+1:02}", bars, parts, 3, 225
    for i in range(3):
        bars = [stock(j, "maple", rng.randrange(1300, 3200),
                      "remnant" if j < 5 else "stock") for j in range(13)]
        parts = [demand(j, "maple", rng.randrange(200, 1100)) for j in range(25)]
        yield f"dense-{i+1:02}", bars, parts, 3, 500
    yield ("unfillable-profile", [stock(0, "oak", 2400)], [demand(0, "ash", 200)], 3, 225)


def first_fit(stocks, parts, kerf, reuse):
    """Longest demand first, scan remnants then full lengths in inventory order."""
    order = sorted(stocks, key=lambda bar: bar["kind"] == "stock")
    tails = {bar["id"]: bar["length_mm"] for bar in stocks}
    used = set()
    lost_in_kerfs = 0
    for row in sorted(parts, key=lambda row: -row["length_mm"]):
        for _ in range(row["qty"]):
            need = row["length_mm"] + kerf
            for bar in order:
                key = bar["id"]
                if bar["material"] == row["material"] and tails[key] >= need:
                    tails[key] -= need
                    used.add(key)
                    lost_in_kerfs += kerf
                    break
            else:
                return None
    fresh = sum(bar["kind"] == "stock" and bar["id"] in used for bar in stocks)
    loss = lost_in_kerfs + sum(tails[key] for key in used if tails[key] < reuse)
    return [fresh, loss, len(used)]


def score(metrics):
    return [metrics[k] for k in ("fresh_bars", "loss_mm", "bars_used")]


def measure(seed, limit):
    cases = []
    for name, bars, parts, kerf, reuse in fixtures(seed):
        start = perf_counter()
        reference = first_fit(bars, parts, kerf, reuse)
        baseline_ms = (perf_counter() - start) * 1000
        start = perf_counter()
        result = solve(bars, parts, kerf, reuse, node_limit=limit)
        solve_ms = (perf_counter() - start) * 1000
        objective = None
        if result["status"] in {"optimal", "feasible"}:
            verdict = verify(bars, parts, kerf, reuse, result)
            if not verdict["valid"]:
                raise RuntimeError(f"case {name} rejected: {verdict['errors']}")
            objective = score(result["metrics"])
            if result["baseline"] and objective > score(result["baseline"]):
                raise RuntimeError(f"case {name} discarded its initial solution")
        cases.append({"case": name, "status": result["status"], "nodes": result["nodes"],
                      "first_fit": reference, "solver": objective,
                      "first_fit_ms": round(baseline_ms, 4), "solve_ms": round(solve_ms, 3)})
    paired = [row for row in cases if row["solver"] is not None and row["first_fit"] is not None]
    times = sorted(row["solve_ms"] for row in cases)
    return {
        "format": "offcut-atlas/benchmark/1",
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "seed": seed, "node_limit_per_case": limit, "case_count": len(cases),
        "status_counts": dict(Counter(row["status"] for row in cases)),
        "objective_order": ["fresh_bars", "loss_mm", "bars_used"],
        "comparison": {"paired": len(paired),
                       "improved": sum(row["solver"] < row["first_fit"] for row in paired),
                       "tied": sum(row["solver"] == row["first_fit"] for row in paired),
                       "worse": sum(row["solver"] > row["first_fit"] for row in paired)},
        "median_solve_ms": round(statistics.median(times), 3), "max_solve_ms": max(times),
        "cases": cases,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=614)
    parser.add_argument("--node-limit", type=int, default=60000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.node_limit < 1:
        parser.error("--node-limit must be positive")
    report = json.dumps(measure(args.seed, args.node_limit), indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
