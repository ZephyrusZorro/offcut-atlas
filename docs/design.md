# Offcut Atlas • design record

A framing studio needs to allocate finite lengths of one-dimensional moulding to commissions. The planner uses an inventory of individually identified rails, requested finished lengths, a measured allowance per piece and a minimum useful return length. The operator enters the full material/profile code to establish compatibility. All dimensions are integer millimetres.

## Acceptance criteria set before implementation

1. Every feasible plan covers the order exactly and conserves each opened rail across parts, kerf and tail. An independent reconstruction rejects a modified cut.
2. The bounded search compares against a reproducible greedy allocation and labels budget-limited outcomes explicitly. Exhaustive tiny instances check objective quality.
3. Competing plans may preview the same rail. Only one may book it. A duplicate commit returns its original receipt. Returned stock points to its parent rail and source job.
4. Durable jobs survive restart. Stale worker results cannot overwrite a reclaimed job. Invalid input cannot mutate inventory.
5. A user can edit demand, run it, inspect a scaled cut map and its evidence, compare the next order under two retention thresholds, and download a separately checkable packet.
6. A clean Python checkout must run locally without keys, network calls, model downloads, or a package install. Browser checks cover desktop and mobile layouts.
7. Supply a reproducible benchmark, controlled test evidence and a hands-on walkthrough. Measure only on identifiable fixtures.

## Discovery

| Candidate | What could be verified here | Main unknown |
| --- | --- | --- |
| Transit timed-transfer coordinator | A schedule replay and interchange graph | Rider counts and actual dwell/delay distributions determine whether holding a service helps. [GTFS schedule reference](https://gtfs.org/documentation/schedule/reference/) |
| Food-rescue allocation | A capacitated route and capacity constraints | Fulfilment depends on donation windows, perishable conditions and operating partners. [Bogotá food bank routing study](https://www.mdpi.com/2071-1050/18/2/848) |
| Reusable framing material | Physical accounting, solution quality on small instances, concurrent booking and two-order effects | Real production would need measured losses, material grading and demand history. |

The third direction has a complete local feedback loop. A residual length becomes a named, consumable input to the next order. The distinction between trim loss and usable leftovers comes directly from cutting-stock literature. [One-dimensional usable leftovers](https://www.sciencedirect.com/science/article/pii/S0377221709007966)

PackingSolver supports many geometries and separates instances from solutions. SCIP’s binpacking example uses branch-and-price. These informed the instance/plan boundary and the decision to limit problem sizes. We use an original, bounded one-dimensional implementation with inventory identities so the owner can reproduce and verify allocations with standard Python. No third-party solver code or datasets were incorporated. [PackingSolver](https://github.com/fontanf/packingsolver) · [SCIP binpacking](https://www.scipopt.org/doc/html/BINPACKING_MAIN.php)

Work on uncertainty and usable leftovers motivates the second-order replay. Our two-order experiment answers a conditional question on specified demand. It does not estimate future demand. [Multi-period reuse research](https://doi.org/10.1016/j.cie.2023.109705)

## Design choices

One browser client, one local HTTP service, one durable SQLite ledger and a worker with a time-limited claim. The solver proposes an allocation. An independently implemented verifier checks it. Only the transaction layer can consume rails or issue remnants. The what-if engine runs on copies of stored snapshots. This separation supports meaningful disagreement between planner and verifier with no language model in the accounting path.

A cut incurs one configured allowance for each requested piece, including the last. The ordering of cut labels on a diagram defines a reproducible allocation. It is not a machining sequence. The model assumes one usable linear length per rail and does not model mitres, angled end losses, defects, grain matching, splices or tool settings.
