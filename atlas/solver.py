"""Deterministic, finite-inventory, one-dimensional cutting-stock planner."""

from __future__ import annotations

from ._cut_model import Bar, Piece, Result, Stock, group_inputs, integer, measure, render
from ._cut_refine import refine

Assignment = tuple[int, ...]
Score = tuple[int, int, int]


def _greedy(bars: list[Stock], pieces: list[Piece], strategy: str, reuse: int) -> Assignment | None:
    remaining = [bar.length for bar in bars]
    order: list[int] = []
    for piece in pieces:
        choices = [i for i, tail in enumerate(remaining) if tail >= piece.gross]
        if not choices:
            return None

        def rank(i: int) -> tuple:
            unopened = remaining[i] == bars[i].length
            after = remaining[i] - piece.gross
            if strategy == "first":
                return unopened, i
            if strategy == "best":
                return unopened and bars[i].fresh, after, i
            return unopened and bars[i].fresh, 0 < after < reuse, unopened, after, i

        index = min(choices, key=rank)
        remaining[index] -= piece.gross
        order.append(index)
    return tuple(order)


def _score(bars: list[Stock], tails: list[int], reuse: int) -> Score:
    fresh = scrap = used = 0
    for bar, tail in zip(bars, tails, strict=True):
        if tail < bar.length:
            fresh += bar.fresh
            scrap += tail if tail < reuse else 0
            used += 1
    # Kerf is identical for every complete assignment of this order.
    return fresh, scrap, used


def _minimum_count(lengths: list[int], deficit: int) -> int:
    """Optimistic bar count for a residual demand that may be split arbitrarily."""
    if deficit <= 0:
        return 0
    for count, length in enumerate(sorted(lengths, reverse=True), 1):
        deficit -= length
        if deficit <= 0:
            return count
    return len(lengths) + 1


class _Search:
    def __init__(self, bars: list[Stock], pieces: list[Piece], reuse: int, budget: int):
        self.bars = bars
        self.pieces = pieces
        self.reuse = reuse
        self.budget = budget
        self.nodes = 0
        self.exhausted = True
        self.best: Assignment | None = None
        self.score: Score | None = None
        self.tails = [bar.length for bar in bars]
        self.path: list[int] = []
        self.memo: set[tuple[int, ...]] = set()
        # Bound transposition storage independently of node budget.
        self.memo_limit = max(1, min(8000, 180000 // max(1, len(bars))))
        self.demand = [0] * (len(pieces) + 1)
        for i in range(len(pieces) - 1, -1, -1):
            self.demand[i] = self.demand[i + 1] + pieces[i].gross

    def seed(self, assignment: Assignment | None) -> None:
        if assignment is None:
            return
        tails = [bar.length for bar in self.bars]
        for piece, index in zip(self.pieces, assignment, strict=True):
            tails[index] -= piece.gross
        score = _score(self.bars, tails, self.reuse)
        if self.score is None or score < self.score:
            self.score, self.best = score, assignment

    def lower_bound(self, depth: int) -> Score:
        deficit = self.demand[depth]
        smallest = self.pieces[-1].gross
        opened = fresh = trapped_scrap = remnant_supply = 0
        unopened: list[int] = []
        new_stock: list[int] = []
        for bar, tail in zip(self.bars, self.tails, strict=True):
            if tail < bar.length:
                opened += 1
                fresh += bar.fresh
                if tail >= smallest:
                    deficit -= tail
                elif tail < self.reuse:
                    trapped_scrap += tail
            elif tail >= smallest:
                unopened.append(tail)
                if bar.fresh:
                    new_stock.append(tail)
                else:
                    remnant_supply += tail
        return (
            fresh + _minimum_count(new_stock, deficit - remnant_supply),
            trapped_scrap,
            opened + _minimum_count(unopened, deficit),
        )

    def visit(self, depth: int = 0) -> None:
        if self.nodes >= self.budget:
            self.exhausted = False
            return
        self.nodes += 1
        if depth == len(self.pieces):
            score = _score(self.bars, self.tails, self.reuse)
            if self.score is None or score < self.score:
                self.score, self.best = score, tuple(self.path)
            return

        if self.score is not None and self.lower_bound(depth) >= self.score:
            return

        # The remaining capacity, kind and open flag fully determine future choices.
        # Total capacity falls strictly with every piece, so it also determines depth.
        key = tuple(sorted(
            (tail << 2) + (int(bar.fresh) << 1) + (tail < bar.length)
            for bar, tail in zip(self.bars, self.tails, strict=True)
        ))
        if key in self.memo:
            return
        if len(self.memo) == self.memo_limit:
            self.memo.clear()
        self.memo.add(key)

        load = self.pieces[depth].gross
        choices: list[tuple[bool, bool, int, int]] = []
        equivalents: set[tuple[bool, bool, int]] = set()
        for i, (bar, tail) in enumerate(zip(self.bars, self.tails, strict=True)):
            if tail < load:
                continue
            unopened = tail == bar.length
            state = bar.fresh, unopened, tail
            if state in equivalents:
                continue
            equivalents.add(state)
            after = tail - load
            choices.append((unopened and bar.fresh, 0 < after < self.reuse, after, i))
        for *_, i in sorted(choices):
            self.path.append(i)
            self.tails[i] -= load
            self.visit(depth + 1)
            self.tails[i] += load
            self.path.pop()
            if not self.exhausted:
                break


def solve(stocks: list[dict], parts: list[dict], kerf_mm: int, reuse_mm: int,
          *, node_limit: int = 60000) -> Result:
    """Plan a complete order. IDs and tie breaks are deterministic across input ordering."""
    kerf = integer("kerf_mm", kerf_mm, 0)
    reuse = integer("reuse_mm", reuse_mm, 1)
    limit = integer("node_limit", node_limit, 0)
    groups = list(group_inputs(stocks, parts, kerf))
    catalog: dict[str, Stock] = {}
    plan: list[Bar] = []
    baseline: list[Bar] = []
    baseline_complete = True
    proven = True
    missing: list[str] = []
    nodes = 0

    def failure(status, message) -> Result:
        return {"status": status, "bars": [], "metrics": None, "baseline": None,
                "nodes": nodes, "message": message}

    for material, bars, pieces in groups:
        if max((bar.length for bar in bars), default=0) < pieces[0].gross:
            return failure("infeasible", f"No {material} bar fits the longest piece including kerf.")
        if sum(bar.length for bar in bars) < sum(piece.gross for piece in pieces):
            return failure("infeasible", f"Total {material} length is insufficient after kerf.")
        # Every piece at least this long consumes one slot. Counting slots as if
        # every such piece had exactly the threshold length is an upper bound.
        for count, piece in enumerate(pieces, 1):
            if count < len(pieces) and pieces[count].gross == piece.gross:
                continue
            slots = sum(bar.length // piece.gross for bar in bars)
            if slots < count:
                return failure("infeasible",
                               f"{material} requires {count} pieces of at least {piece.gross} mm "
                               f"including kerf. The available bars fit at most {slots}.")

    for index, (material, bars, pieces) in enumerate(groups):
        catalog.update((bar.id, bar) for bar in bars)
        budget = (limit - nodes) // (len(groups) - index)
        search = _Search(bars, pieces, reuse, budget)
        first = _greedy(bars, pieces, "first", reuse)
        if first is None:
            baseline_complete = False
        else:
            baseline.extend(render(bars, pieces, first))
        search.seed(first)
        for strategy in ("best", "preserve"):
            search.seed(_greedy(bars, pieces, strategy, reuse))
        if search.best is not None:
            search.seed(refine(bars, pieces, search.best, reuse))
        initial = search.best
        search.visit()
        if not search.exhausted and search.best is not None and search.best != initial:
            search.seed(refine(bars, pieces, search.best, reuse))
        nodes += search.nodes
        if search.best is None:
            if search.exhausted:
                return failure("infeasible", f"No complete assignment fits the available {material} bars.")
            missing.append(material)
        else:
            plan.extend(render(bars, pieces, search.best))
        proven &= search.exhausted

    if missing:
        return failure("unknown", "Search budget reached before finding a complete plan for "
                       + ", ".join(missing) + ".")
    return {
        "status": "optimal" if proven else "feasible",
        "bars": plan,
        "metrics": measure(plan, catalog, kerf, reuse),
        "baseline": measure(baseline, catalog, kerf, reuse) if baseline_complete else None,
        "nodes": nodes,
        "message": ("Best possible under the selected stock and rules." if proven else
                    "Complete plan found within budget. Optimality remains unproven."),
    }
