"""Run two retention policies on identical order pairs and inventory copies."""
from .proof import verify
from .solver import solve
from .validation import Problem, demand, fields, integer


def scenario(run, body):
    fields(body, ("threshold_a", "threshold_b", "next_order"))
    policies = [integer(body[k], k, 1, 10000) for k in ("threshold_a", "threshold_b")]
    if policies[0] == policies[1]:
        raise Problem(422, "equal_thresholds", "Choose two different retention thresholds.")
    following = demand(body["next_order"])
    return {"run_id": run["id"], "revision": run["revision"],
            "order_names": [run["request"]["name"], following["name"]],
            "policies": [project(run["stocks"], [run["request"], following], threshold) for threshold in policies]}


def project(snapshot, orders, threshold):
    rack = {r["id"]: r for r in snapshot}
    history = []
    totals = {"fresh_bars": 0, "loss_mm": 0, "parts_mm": 0}
    for index, order in enumerate(orders, 1):
        stock = list(rack.values())
        plan = solve(stock, order["parts"], order["kerf_mm"], threshold, node_limit=4000)
        stage = {"name": order["name"], "status": plan["status"], "message": plan["message"],
                 "metrics": plan.get("metrics"), "bars": plan["bars"], "returned": [], "nodes": plan["nodes"]}
        history.append(stage)
        if plan["status"] not in ("optimal", "feasible"):
            break
        certificate = verify(stock, order["parts"], order["kerf_mm"], threshold, plan)
        if not certificate["valid"]:
            raise Problem(500, "replay_proof", "Material accounting failed during the replay.")
        stage["digest"] = certificate["digest"]
        for field in totals:
            totals[field] += plan["metrics"][field]
        for bar in plan["bars"]:
            parent = rack.pop(bar["stock_id"])
            tail = bar["tail_mm"]
            if tail >= threshold:
                key = f"sim-{index}-{parent['id']}"
                remnant = dict(id=key, material=parent["material"], length_mm=tail, kind="remnant")
                rack[key] = remnant
                stage["returned"].append(dict(parent_id=parent["id"], length_mm=tail, material=parent["material"]))
    complete = len(history) == len(orders) and all("digest" in stage for stage in history)
    return dict(threshold_mm=threshold, complete=complete, stages=history,
                totals=totals if complete else None, ending_rails=len(rack))


def compare_horizon(source, snapshot, orders, threshold):
    from .horizon import lookahead

    sequential = project(snapshot, orders, threshold)
    if sequential["complete"]:
        sequential["totals"]["bars_used"] = sum(s["metrics"]["bars_used"] for s in sequential["stages"])
    return dict(source=source, threshold_mm=threshold, orders=[o["name"] for o in orders],
                sequential=sequential, joint=lookahead(snapshot, orders, threshold))


def lookahead_run(run, body):
    fields(body, ("threshold_mm", "next_order"))
    threshold = integer(body["threshold_mm"], "Retention threshold", 1, 10000)
    orders = [run["request"], demand(body["next_order"])]
    return compare_horizon(run["name"], run["stocks"], orders, threshold)
