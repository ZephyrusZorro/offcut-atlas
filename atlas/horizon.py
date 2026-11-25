"""Jointly allocate two known orders, with an actual stock transition between them."""
from ._cut_model import Stock, measure
from .proof import verify
from .solver import solve

OBJECTIVE = ("fresh_bars", "loss_mm", "bars_used")


def after_order(stock, bars, threshold):
    allocated = {bar["stock_id"]: bar for bar in bars}
    rack, returned = [], []
    occupied = {r["id"] for r in stock}
    for rail in stock:
        key = rail["id"]
        if key not in allocated:
            rack.append(rail)
        elif (tail := allocated[key]["tail_mm"]) >= threshold:
            child = "next-" + key
            while child in occupied:
                child = "next-" + child
            occupied.add(child)
            row = dict(id=child, material=rail["material"], kind="remnant", length_mm=tail, parent_id=key)
            rack.append(row)
            returned.append(row)
    return rack, returned


def allocations(stock, order, threshold, budget):
    """Yield first- or second-order witnesses, symmetrically pruning equivalent rails."""
    pieces = sorted((p for p in order["parts"] for _ in range(p["qty"])),
                    key=lambda p: (-p["length_mm"], p["id"]))
    tails = [s["length_mm"] for s in stock]
    cuts = [[] for _ in stock]

    def visit(depth):
        if budget["nodes"] >= budget["limit"]:
            budget["truncated"] = True
            return
        budget["nodes"] += 1
        if depth == len(pieces):
            yield [dict(stock_id=s["id"], cuts=list(cuts[i]), tail_mm=tails[i])
                   for i, s in enumerate(stock) if cuts[i]]
            return
        part = pieces[depth]
        gross = part["length_mm"] + order["kerf_mm"]
        symmetry = set()
        for i, rail in enumerate(stock):
            if rail["material"] != part["material"] or tails[i] < gross:
                continue
            signature = rail["kind"], tails[i], bool(cuts[i]), rail["length_mm"]
            if signature in symmetry:
                continue
            symmetry.add(signature)
            tails[i] -= gross
            cuts[i].append(dict(part_id=part["id"], length_mm=part["length_mm"]))
            yield from visit(depth+1)
            cuts[i].pop()
            tails[i] += gross
            if budget["truncated"]:
                return
    yield from visit(0)


def metrics(stock, bars, order, threshold):
    index = {s["id"]: Stock(s["id"],s["length_mm"],s["kind"] == "stock") for s in stock}
    return measure(bars,index,order["kerf_mm"],threshold)


def lookahead(stocks, orders, threshold, *, node_limit=20000):
    materials = {p["material"] for order in orders for p in order["parts"]}
    rack = sorted((r for r in stocks if r["material"] in materials), key=lambda r:r["id"])
    count = sum(p["qty"] for order in orders for p in order["parts"])
    if len(orders) != 2 or len(rack)>7 or count>10:
        return dict(status="too_large", nodes=0, totals=None, stages=[],
                    message="Joint search accepts two orders, up to seven matching rails and ten pieces in total.")

    best = None
    winner = None
    def consider(pair):
        nonlocal best, winner
        score = tuple(sum(stage[2][k] for stage in pair) for k in OBJECTIVE)
        if best is None or score < best:
            best, winner = score, pair

    # Start with a complete sequential witness whenever the bounded planner has one.
    first, second = orders
    seed = []
    current = rack
    for order in orders:
        plan = solve(current, order["parts"], order["kerf_mm"], threshold, node_limit=4000)
        if plan["status"] not in ("optimal", "feasible"):
            break
        seed.append((current, plan["bars"], plan["metrics"]))
        current, _ = after_order(current, plan["bars"], threshold)
    if len(seed) == 2:
        consider(seed)

    budget = dict(limit=node_limit, nodes=0, truncated=False)
    for one in allocations(rack, first, threshold, budget):
        summary = metrics(rack, one, first, threshold)
        if best and summary["fresh_bars"] > best[0]:
            continue
        carried, _ = after_order(rack, one, threshold)
        for two in allocations(carried, second, threshold, budget):
            consider([(rack, one, summary), (carried, two, metrics(carried,two,second,threshold))])
        if budget["truncated"]:
            break
    if winner is None:
        status = "unknown" if budget["truncated"] else "infeasible"
        return dict(status=status, nodes=budget["nodes"], stages=[], totals=None,
                    message="Search budget reached without a complete pair." if status=="unknown"
                    else "No pair of allocations can fill both orders from these rails.")

    stages = []
    for order,(stock,bars,totals) in zip(orders,winner,strict=True):
        result = dict(status="feasible", bars=bars, metrics=totals, baseline=None,
                      nodes=budget["nodes"], message="Stage of a verified two-order allocation.")
        proof = verify(stock,order["parts"],order["kerf_mm"],threshold,result)
        if not proof["valid"]:
            raise ValueError("Joint allocation failed stage verification.")
        _, returned = after_order(stock,bars,threshold)
        stages.append(dict(name=order["name"], stocks=stock, bars=bars, metrics=totals,
                           verification=proof, returned=returned, result=result))
    return dict(status="feasible" if budget["truncated"] else "optimal", nodes=budget["nodes"],
                totals=dict(zip(OBJECTIVE,best,strict=True)), stages=stages,
                message="Verified pair. The search budget limits its optimality claim." if budget["truncated"]
                else "Optimal across both orders under this snapshot, allowance and retention rule.")
