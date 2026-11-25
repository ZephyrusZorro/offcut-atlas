"""Physical units, solver input checks and the public plan representation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Literal, TypedDict


@dataclass(frozen=True, slots=True)
class Stock:
    id: str
    length: int
    fresh: bool


@dataclass(frozen=True, slots=True)
class Piece:
    id: str
    length: int
    gross: int


class Cut(TypedDict):
    part_id: str
    length_mm: int


class Bar(TypedDict):
    stock_id: str
    cuts: list[Cut]
    tail_mm: int


class Metrics(TypedDict):
    fresh_bars: int
    loss_mm: int
    bars_used: int
    parts_mm: int
    kerf_mm: int
    reusable_mm: int
    stock_mm: int


class Result(TypedDict):
    status: Literal["optimal", "feasible", "infeasible", "unknown"]
    bars: list[Bar]
    metrics: Metrics | None
    baseline: Metrics | None
    nodes: int
    message: str


def integer(name: str, value: object, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer of at least {minimum}")
    return value


def identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def group_inputs(stocks: list[dict], parts: list[dict], kerf: int):
    if not isinstance(stocks, list) or not isinstance(parts, list):
        raise ValueError("stocks and parts must be lists")
    if len(stocks) > 128:
        raise ValueError("at most 128 stock rows are supported")
    stock_groups: dict[str, list[Stock]] = defaultdict(list)
    part_groups: dict[str, list[Piece]] = defaultdict(list)
    part_count = 0
    for rows, is_stock in ((stocks, True), (parts, False)):
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("each row must be an object")
            key = identifier("id", row.get("id"))
            material = identifier("material", row.get("material"))
            length = integer("length_mm", row.get("length_mm"), 1)
            if key in seen:
                raise ValueError(f"duplicate id {key!r}")
            seen.add(key)
            if is_stock:
                if row.get("kind") not in ("stock", "remnant"):
                    raise ValueError("kind must be stock or remnant")
                stock_groups[material].append(Stock(key, length, row["kind"] == "stock"))
            else:
                quantity = integer("qty", row.get("qty"), 1)
                part_count += quantity
                if part_count > 160:
                    raise ValueError("at most 160 individual pieces are supported")
                part_groups[material].extend([Piece(key, length, length + kerf)] * quantity)
    for material in sorted(part_groups):
        bars = sorted(stock_groups[material], key=lambda bar: (bar.fresh, bar.id))
        pieces = sorted(part_groups[material], key=lambda part: (-part.gross, part.id))
        yield material, bars, pieces


def render(bars: list[Stock], pieces: list[Piece], assignment: tuple[int, ...]) -> list[Bar]:
    cuts: dict[int, list[Cut]] = {}
    loads: dict[int, int] = defaultdict(int)
    for piece, index in zip(pieces, assignment, strict=True):
        cuts.setdefault(index, []).append({"part_id": piece.id, "length_mm": piece.length})
        loads[index] += piece.gross
    return [
        {"stock_id": bars[i].id, "cuts": cuts[i], "tail_mm": bars[i].length - loads[i]}
        for i in sorted(cuts)
    ]


def measure(plan: list[Bar], stocks: dict[str, Stock], kerf: int, reuse: int) -> Metrics:
    parts = sum(cut["length_mm"] for bar in plan for cut in bar["cuts"])
    saw_loss = kerf * sum(len(bar["cuts"]) for bar in plan)
    scrap = sum(bar["tail_mm"] for bar in plan if bar["tail_mm"] < reuse)
    return {
        "fresh_bars": sum(stocks[bar["stock_id"]].fresh for bar in plan),
        "loss_mm": saw_loss + scrap,
        "bars_used": len(plan),
        "parts_mm": parts,
        "kerf_mm": saw_loss,
        "reusable_mm": sum(bar["tail_mm"] for bar in plan if bar["tail_mm"] >= reuse),
        "stock_mm": sum(stocks[bar["stock_id"]].length for bar in plan),
    }
