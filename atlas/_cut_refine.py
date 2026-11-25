"""Best-improvement moves and exchanges on a complete, material-compatible plan."""

from ._cut_model import Piece, Stock


def refine(bars: list[Stock], pieces: list[Piece], assignment: tuple[int, ...],
           reuse: int) -> tuple[int, ...]:
    placement = list(assignment)
    tails = [bar.length for bar in bars]
    for piece, index in zip(pieces, placement, strict=True):
        tails[index] -= piece.gross

    def contribution(index: int, tail: int) -> tuple[int, int, int]:
        if tail == bars[index].length:
            return 0, 0, 0
        return int(bars[index].fresh), tail if tail < reuse else 0, 1

    count = len(pieces)
    neighborhood_size = count * len(bars) + count * (count - 1) // 2
    passes = max(1, min(12, 120000 // max(1, neighborhood_size)))
    for _ in range(passes):
        contributions = [contribution(i, tail) for i, tail in enumerate(tails)]
        best_delta = (0, 0, 0)
        best_move = None
        # Equal-size pieces in the same source produce the same neighborhood.
        with_load: dict[tuple[int, int], int] = {}
        for i, piece in enumerate(pieces):
            with_load.setdefault((placement[i], piece.gross), i)
        representatives = list(with_load.items())
        for index, ((source, load), i) in enumerate(representatives):
            def consider(target: int, gain: int, j: int | None) -> None:
                nonlocal best_move, best_delta
                left = contribution(source, tails[source] + gain)
                right = contribution(target, tails[target] - gain)
                a, b = contributions[source], contributions[target]
                delta = (left[0] + right[0] - a[0] - b[0],
                         left[1] + right[1] - a[1] - b[1],
                         left[2] + right[2] - a[2] - b[2])
                if delta < best_delta:
                    best_delta = delta
                    best_move = i, source, target, gain, j

            for target, tail in enumerate(tails):
                if source != target and tail >= load:
                    consider(target, load, None)
            for (target, other_load), j in representatives[index + 1:]:
                gain = load - other_load
                if (source != target and gain != 0 and
                        tails[source] + gain >= 0 and tails[target] >= gain):
                    consider(target, gain, j)
        if best_move is None:
            break
        i, source, target, gain, j = best_move
        placement[i] = target
        if j is not None:
            placement[j] = source
        tails[source] += gain
        tails[target] -= gain
    return tuple(placement)
