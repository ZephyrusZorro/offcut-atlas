# Checking an allocation independently

A studio can download its run packet and check it on a second computer. The checker takes the inventory snapshot, original part rows, allowances and proposed assignment from the packet. Its only dependency is Python. It does not open the ledger, start a web server or import the planner.

```console
python -m atlas.check packet.json
python -m atlas.check packet.json --expect-digest <trusted-sha256>
```

The command prints a JSON verdict. Exit code 0 means all feasibility checks and the requested digest comparisons passed. Exit code 1 reports the first failed check. Renaming a demand label leaves the material accounting intact but changes the digest. Changing a cut length can invalidate both. The optional reference digest is useful when retained separately from the packet.

## What the checker reconstructs

Each covered demand ID has the exact requested number of pieces. Each assigned inventory ID occurs in one bar. Every cut has its requested material and finished length. Every per-bar tail is a nonnegative integer, and the sum of finished pieces, per-piece kerf and tail equals the original bar length.

Integer units avoid rounding at the retention boundary. A tail exactly equal to the retention threshold is reusable. Across all opened bars, the checker independently reconstructs the following totals.

| Quantity | Calculation |
| --- | --- |
| Fresh bars | Opened rails with kind `stock` |
| Loss | Kerf plus tails below the retention threshold |
| Bars used | Count of distinct opened inventory IDs |
| Finished length | Sum of physical cut lengths |
| Kerf | Number of cuts multiplied by the configured kerf |
| Reusable length | Sum of qualifying tails |
| Stock length | Original length of every opened rail added once |

The redundant totals provide independent cross-checks against UI or persistence errors. In particular, finished length + reusable length + loss = stock length. The checker also requires one feasible or optimal result with well-formed planner metadata.

## Digest scope and trust

The versioned digest covers all stock rows (including source IDs when supplied), part rows (including labels), kerf, retention threshold and the entire solver result. Canonicalization uses Python JSON with lexicographically sorted object keys, compact separators, ASCII escaping and finite numbers. Array order is preserved. SHA-256 is applied to that ASCII byte sequence. The digest input contains these six keys:

```json
{"format":"offcut-atlas/proof/1","stocks":[],"parts":[],"kerf_mm":3,"reuse_mm":225,"result":{}}
```

This illustrates the envelope. A real certificate needs demand and a complete feasible assignment. The CLI rejects duplicate JSON object keys. Run ID, display name, event history, booking receipt and previously reported checks are outside the digest. The feasibility result concerns the captured snapshot, so current availability still depends on booking through the ledger.

The checker attests physical feasibility within the model. The solver supplies the optimality status, baseline and search-node count. Checking a hash detects changes against a retained reference. Anyone who edits a packet can also recalculate its hash. Verifying publisher identity would require an authenticated channel or a digital signature.

## Reproducible evaluation

```console
python tools/benchmark.py --seed 614 --node-limit 60000 --output benchmark.json
python -m unittest discover -s tests -p test_proof.py -v
```

The benchmark compares the solver with a separately coded first-fit rule. The reference consumes the longest required pieces first, scanning compatible remnants and then full rails in inventory order. Its tie-breaking differs from the baseline reported within a live plan. The benchmark reports both runtimes, solution status, explored nodes and the compound score for each case. Lower scores win lexicographically by fresh bars, irreversible loss in millimetres, then total rails opened. Every solver allocation undergoes independent feasibility verification before inclusion.

The first fixture makes the optimization tangible. Six pieces including their kerfs require 600, 500, 300, 200, 200 and 200 mm. First fit opens three 1,000 mm rails. The best assignment packs (600, 200, 200) and (500, 300, 200) into two. At 3 mm per piece and a 125 mm retention threshold, this saves one rail and reduces modeled irreversible loss from 218 mm to 18 mm.

Twelve mixed-profile fixtures vary remnant sizes and demand on an ash and oak rack. Three denser maple jobs give the planner 25 pieces and 13 rails with disparate lengths. The final fixture requests an absent profile. These deterministic, synthetic examples exercise allocation and accounting. They measure neither real workshop yield nor the duration of a complete HTTP workflow.

### Recorded results · 25 November 2026

One local run on Windows 11 build 26300 and CPython 3.12.9 used the command above. All 16 returned allocations passed independent reconstruction. The solver reported 13 optimal allocations, three feasible allocations with the 60,000-node limit reached and one infeasible case. The median solver call across all 17 cases took 0.361 ms. The slowest took 146.395 ms. These are single-pass, in-process measurements including the deliberate immediate rejection case.

| Cohort | Results against first fit | Status |
| --- | --- | --- |
| Packing counterexample | One improvement | 1 optimal |
| Mixed profiles | Eleven improvements, one tie | 12 optimal |
| Dense single profile | Three improvements | 3 feasible |
| Missing profile | Both methods found no allocation | 1 infeasible |

The initial bounded solver lost to first fit on dense-02. It used three fresh rails and lost 722 mm, while first fit used three and lost 648 mm. After adding piece relocation and exchange to improve incumbents, the same seed and search limit produced a verified plan using three fresh rails with 173 mm of loss.

Additional runs used `--seed 615`, `--seed 616` and `--seed 617`. Excluding the two repeated fixed fixtures per seed left 45 new comparisons. The solver improved 44 and lost one. On seed 615, dense-03, first fit used two fresh rails and the bounded solver used four. Both returned feasible assignments. The rack order used by the external reference can favor a packing that the bounded search does not reach.

In a separate integration check, a fresh synthetic ledger produced a Northlight packet accepted by `python -m atlas.check`. Changing one demand label caused exit code 1. The eight checker tests cover all seven reconstructed totals, duplicate assignments, material and dimension mismatches, underfilled demand, threshold equality, boolean and floating-point substitutions, malformed packets, digest stability and independently supplied reference digests.
