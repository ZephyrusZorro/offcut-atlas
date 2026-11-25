"""Validation shared by intake, durable jobs and what-if experiments."""
import re
import unicodedata


class Problem(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code


def invalid(message):
    raise Problem(422, "invalid_input", message)


def fields(value, required):
    if not isinstance(value, dict) or set(value) != set(required):
        invalid("Expected exactly these fields: " + ", ".join(required))


def string(value, field, limit=96):
    if not isinstance(value, str):
        invalid(f"{field} must be text.")
    value = value.strip()
    if not 1 <= len(value) <= limit or any(unicodedata.category(c).startswith("C") for c in value):
        invalid(f"{field} must contain 1 to {limit} printable characters.")
    return value


def integer(value, field, lo, hi):
    if type(value) is not int or not lo <= value <= hi:
        invalid(f"{field} must be an integer from {lo} to {hi}.")
    return value


def material(value):
    return unicodedata.normalize("NFC", string(value, "Material", 64))


def demand(value):
    fields(value, ("name", "parts", "kerf_mm", "reuse_mm"))
    name = string(value["name"], "Order name")
    kerf = integer(value["kerf_mm"], "Kerf", 0, 20)
    reuse = integer(value["reuse_mm"], "Retention threshold", 1, 10000)
    if not isinstance(value["parts"], list) or not 1 <= len(value["parts"]) <= 48:
        invalid("An order needs 1 to 48 part rows.")
    parts, seen = [], set()
    for row in value["parts"]:
        fields(row, ("id", "label", "material", "length_mm", "qty"))
        key = string(row["id"], "Part ID", 64)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", key) or key in seen:
            invalid("Part IDs must be unique and use letters, digits, dots, dashes or underscores.")
        seen.add(key)
        parts.append(dict(id=key, label=string(row["label"], "Label"),
                          material=material(row["material"]),
                          length_mm=integer(row["length_mm"], "Part length", 1, 100000),
                          qty=integer(row["qty"], "Quantity", 1, 96)))
    if sum(row["qty"] for row in parts) > 96:
        invalid("The local planner supports at most 96 finished pieces per order.")
    return dict(name=name, parts=parts, kerf_mm=kerf, reuse_mm=reuse)


def intake(value):
    fields(value, ("material", "length_mm", "kind", "qty"))
    if value["kind"] not in ("remnant", "stock"):
        invalid("Kind must be stock or remnant.")
    return dict(material=material(value["material"]),
                length_mm=integer(value["length_mm"], "Rail length", 1, 100000),
                kind=value["kind"], qty=integer(value["qty"], "Rail quantity", 1, 32))
