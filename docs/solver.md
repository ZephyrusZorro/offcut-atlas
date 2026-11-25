# How the planner makes a decision

An order line gives a finished rail's required linear allocation in millimetres and its quantity. Each stock record represents one available bar of a single material/profile. Profile keys must distinguish incompatible finishes or cross-sections. A workshop supplies its own allowances for mitres, defects and end trimming when entering dimensions.

## Material accounting

Each individual piece consumes its entered length plus one full kerf, including the last piece on a bar. A tail exactly at the reuse threshold qualifies for return. Stock quantity and bar identities are finite. No purchase is implied by opening a fresh bar.

For every complete plan, `stock_mm = parts_mm + loss_mm + reusable_mm`. The reported loss includes saw kerfs and tails below threshold. Untouched stock stays outside the plan and all its metrics.

The objective is the lexicographic minimum of **fresh bars opened**, **millimetres lost**, and **total bars opened**, in that order. The workshop therefore prefers to draw from remaining stock and can accept greater irreversible loss to avoid opening a fresh bar. Each field is additive across material profiles, so optimizing each compatible group independently preserves the order-wide objective.

## Search

1. Sort demand by descending gross length and break ties by part ID. Reject a profile if its longest cut exceeds the largest bar or its gross requirement exceeds total available length.
2. At each distinct gross demand length `t`, count pieces at least that long. The sum of `floor(bar_length / t)` over all bars is an upper bound on the number that could fit. Violating any such bound proves infeasibility, even with ample total length.
3. Compute a first-fit baseline. Try opened bars first, then unused remnants, then unused fresh bars, with deterministic stock ID ordering within each group. Two further greedy starts prefer tight fits and reusable tails. Keep the best complete solution.
4. Improve the incumbent with strictly beneficial single-piece relocations and two-piece exchanges. Every candidate preserves capacity, stock identity and profile. Bound the number of passes by neighborhood size. This step may find a better solution before tree search starts.
5. Branch on the next piece's destination. Symmetric destinations have identical stock kind, current tail and opened flag. One representative suffices. A bounded cache of sorted capacity states avoids re-solving equivalent subproblems. The cache can be cleared without affecting correctness because expiry only allows repeated work.
6. Prune branches whose optimistic score already meets or exceeds the incumbent. To bound fresh bars, allow all open capacity and remaining remnants for free, then use the longest unused fresh bars. To bound total bars, use longest unopened bars of either kind. Both bounds allow arbitrary splitting and consequently understate the required count. Unusable short tails on opened bars contribute a minimum irreversible loss. Kerf is a fixed charge across all complete assignments for this order.
7. Stop when every branch has been accounted for or the material's node budget is spent. Refine a newly found incumbent again after a truncated search. The default order-wide budget is 60,000 visited nodes, divided among the remaining material groups as they start. The node count covers tree search. Validation, greedy starts and local improvement run separately.

The method takes inspiration from research on usable leftovers and on bounding exact bin-packing searches. This implementation handles finite heterogeneous bar sizes, the workshop's three-part objective and deterministic budgets directly. [Usable leftovers in one-dimensional cutting stock](https://www.sciencedirect.com/science/article/pii/S0377221709007966) · [Schreiber and Korf, IJCAI](https://ijcai.org/proceedings/2013/103)

## Interpreting the result

| Status | What the planner established |
| --- | --- |
| `optimal` | A complete plan exists and the search proved its objective under the supplied model. Several layouts can share that objective. |
| `feasible` | A complete, capacity-respecting plan exists. A budget limit leaves the best achievable objective open. |
| `infeasible` | A necessary physical condition failed or a material's search exhausted every possible assignment. |
| `unknown` | The budget ended before a complete order-wide plan or impossibility proof was available. |

The planner returns the baseline only when first fit completes all order lines. Both unsuccessful statuses return empty plans. A zero node budget still permits structural checks, greedy construction and local improvement. The solver accepts up to 128 stock rows and 160 expanded pieces per invocation. Public service limits can be smaller.

## Reproducible cross-check

Run `python -m unittest discover -s tests -p test_solver.py -v` at the repository root. The oracle covers 160 seeded small orders by enumerating all labeled assignments, independently calculating capacities, compatibility and objective. Targeted tests cover exact kerf, threshold equality, greedy failure, budget exhaustion, mixed material groups and pair exchanges. These checks exercise model correctness on synthetic orders. Actual material condition, cutting accuracy and usable residual length require workshop measurement.

The fragmentation guard arose from a measured failure. With bars of lengths 1,020 through 1,035 mm, an order for seventeen 850 mm rails and a 3 mm kerf initially exhausted 60,000 tree nodes without a decision. The slot bound proves the maximum is sixteen at the root, using zero tree nodes. A second review exposed a budget-limited layout with higher loss than an independent first-fit rule. Local refinement reduced that case from 722 to 173 mm at the same 60,000-node budget. The seeded `dense-02` fixture in `tools/benchmark.py` reproduces the final behavior.
