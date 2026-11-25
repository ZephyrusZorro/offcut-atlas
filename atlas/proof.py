"""Independent, deterministic checker for one-dimensional cut allocations."""

import hashlib
import json
from collections import Counter
from typing import Any


METRICS = (
    "fresh_bars", "loss_mm", "bars_used", "parts_mm", "kerf_mm",
    "reusable_mm", "stock_mm",
)


class InvalidPlan(ValueError):
    """An allocation violates a certificate requirement."""


def _require(condition: bool, error: str) -> None:
    if not condition:
        raise InvalidPlan(error)


def _object(value: Any, context: str) -> dict:
    _require(isinstance(value, dict), f"{context} must be an object")
    return value


def _array(value: Any, context: str) -> list:
    _require(isinstance(value, list), f"{context} must be an array")
    return value


def _integer(value: Any, context: str, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum,
             f"{context} must be an integer of at least {minimum}")
    return value


def _string(value: Any, context: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()),
             f"{context} must be a nonempty string")
    return value


def _index(rows: Any, key: str) -> dict:
    indexed = {}
    for i, row in enumerate(_array(rows, key)):
        ctx = f"{key}[{i}]"
        _object(row, ctx)
        identity = _string(row.get("id"), f"{ctx}.id")
        _require(identity not in indexed, f"duplicate {key} id {identity!r}")
        _string(row.get("material"), f"{ctx}.material")
        _integer(row.get("length_mm"), f"{ctx}.length_mm", 1)
        if key == "stocks":
            _require(row.get("kind") in ("stock", "remnant"), f"{ctx}.kind is invalid")
        else:
            _integer(row.get("qty"), f"{ctx}.qty", 1)
            _string(row.get("label"), f"{ctx}.label")
        indexed[identity] = row
    return indexed


def _reconstruct(stocks: dict, parts: dict, kerf: int, reuse: int, bars: list) -> dict:
    totals = dict.fromkeys(METRICS, 0)
    demand_filled = Counter()
    used = set()
    for i, bar in enumerate(bars):
        ctx = f"bars[{i}]"
        _object(bar, ctx)
        identity = _string(bar.get("stock_id"), f"{ctx}.stock_id")
        _require(identity in stocks, f"unknown stock {identity!r}")
        _require(identity not in used, f"stock {identity!r} assigned twice")
        used.add(identity)
        stock = stocks[identity]
        cuts = _array(bar.get("cuts"), f"{ctx}.cuts")
        _require(bool(cuts), f"stock {identity!r} has no assigned cuts")
        cut_length = 0
        for j, cut in enumerate(cuts):
            ctx_cut = f"{ctx}.cuts[{j}]"
            _object(cut, ctx_cut)
            part_id = _string(cut.get("part_id"), f"{ctx_cut}.part_id")
            _require(part_id in parts, f"unknown part {part_id!r}")
            part = parts[part_id]
            length = _integer(cut.get("length_mm"), f"{ctx_cut}.length_mm", 1)
            _require(length == part["length_mm"], f"length differs for part {part_id!r}")
            _require(part["material"] == stock["material"],
                     f"material mismatch for part {part_id!r} on stock {identity!r}")
            demand_filled[part_id] += 1
            cut_length += length

        measured_tail = _integer(bar.get("tail_mm"), f"{ctx}.tail_mm")
        kerf_length = len(cuts) * kerf
        expected_tail = stock["length_mm"] - cut_length - kerf_length
        _require(expected_tail == measured_tail,
                 f"stock {identity!r} fails length conservation (expected tail {expected_tail})")
        totals["fresh_bars"] += int(stock["kind"] == "stock")
        totals["bars_used"] += 1
        totals["parts_mm"] += cut_length
        totals["kerf_mm"] += kerf_length
        totals["stock_mm"] += stock["length_mm"]
        totals["loss_mm"] += kerf_length
        if measured_tail >= reuse:
            totals["reusable_mm"] += measured_tail
        else:
            totals["loss_mm"] += measured_tail

    for part_id, part in parts.items():
        count = demand_filled[part_id]
        _require(count == part["qty"],
                 f"part {part_id!r} requires {part['qty']} pieces, found {count}")
    return totals


def verify(stocks: list, parts: list, kerf_mm: int, reuse_mm: int, result: dict) -> dict:
    """Rebuild assignment facts from the inputs. No solver imports or mutable state."""
    digest = ""
    checks = []
    try:
        protected = {
            "format": "offcut-atlas/proof/1", "stocks": stocks, "parts": parts,
            "kerf_mm": kerf_mm, "reuse_mm": reuse_mm, "result": result,
        }
        canonical = json.dumps(protected, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False)
        digest = hashlib.sha256(canonical.encode("ascii")).hexdigest()
        stock_index = _index(stocks, "stocks")
        part_index = _index(parts, "parts")
        _integer(kerf_mm, "kerf_mm")
        _integer(reuse_mm, "reuse_mm", 1)
        _require(bool(part_index), "the order must contain at least one part")
        _object(result, "result")
        _require(result.get("status") in ("feasible", "optimal"),
                 "a feasible allocation is required for a certificate")
        _integer(result.get("nodes"), "nodes")
        _string(result.get("message"), "message")
        _require("baseline" in result, "result.baseline is required")
        if result["baseline"] is not None:
            baseline = _object(result["baseline"], "baseline")
            for key in METRICS:
                _integer(baseline.get(key), f"baseline.{key}")
        checks.append("Input schema and unique identifiers")

        totals = _reconstruct(stock_index, part_index, kerf_mm, reuse_mm,
                              _array(result.get("bars"), "bars"))
        checks.extend(["Stock assigned at most once", "Material and cut length match",
                       "Exact demand quantities", "Per-bar kerf and length conservation"])
        metrics = _object(result.get("metrics"), "metrics")
        for name, expected in totals.items():
            recorded = _integer(metrics.get(name), f"metrics.{name}")
            _require(recorded == expected,
                     f"metrics.{name} is {recorded}, expected {expected}")
        checks.append("All seven material and objective totals reconstructed")
    except (InvalidPlan, TypeError, ValueError, RecursionError, OverflowError) as exc:
        return {"valid": False, "digest": digest, "checks": checks, "errors": [str(exc)]}
    return {"valid": True, "digest": digest, "checks": checks, "errors": []}
