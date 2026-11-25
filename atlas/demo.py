"""A synthetic, repeatable exhibition framing commission."""
ORDER = {
    "name": "Northlight exhibition",
    "kerf_mm": 3, "reuse_mm": 300,
    "parts": [
        {"id": "A1", "label": "Panorama · long", "material": "Natural oak", "length_mm": 940, "qty": 4},
        {"id": "A2", "label": "Panorama · short", "material": "Natural oak", "length_mm": 560, "qty": 4},
        {"id": "B1", "label": "Study · long", "material": "Black ash", "length_mm": 720, "qty": 2},
        {"id": "B2", "label": "Study · short", "material": "Black ash", "length_mm": 420, "qty": 2},
    ],
}
# IDs identify physical pieces. Duplicate lengths are independent assets.
RAILS = [
    ("OAK-001", "Natural oak", 3100, "stock"),
    ("OAK-002", "Natural oak", 3100, "stock"),
    ("OAK-003", "Natural oak", 3100, "stock"),
    ("OAK-R01", "Natural oak", 1520, "remnant"),
    ("OAK-R02", "Natural oak", 1190, "remnant"),
    ("ASH-001", "Black ash", 3000, "stock"),
    ("ASH-002", "Black ash", 3000, "stock"),
    ("ASH-R01", "Black ash", 1160, "remnant"),
    ("ASH-R02", "Black ash", 860, "remnant"),
]


def horizon_example():
    """A small synthetic commission that rewards saving a particular remnant."""
    stock = [dict(id=key, material="Maple", length_mm=length, kind=kind) for key, length, kind in (
        ("MAPLE-R", 700, "remnant"), ("MAPLE-A", 1000, "stock"), ("MAPLE-B", 1000, "stock"))]
    orders = []
    for name, lengths in (("Study frame", [397]), ("Exhibition pair", [697, 597])):
        parts = [dict(id=f"P{i}", label=f"Member {i}", material="Maple", length_mm=n, qty=1)
                 for i, n in enumerate(lengths, 1)]
        orders.append(dict(name=name, parts=parts, kerf_mm=3, reuse_mm=200))
    return stock, orders, 200
