# What the two-order replay can establish

The replay answers a studio question: given two specified orders, how would the implemented planner perform at each retention threshold? It plans the first order, carries its qualifying tails to the next rack, then plans the second order. Advance knowledge of the second order can change the best first assignment. Multi-period cutting stock research models that interaction explicitly. [Trkman and Gradišar, “One-dimensional cutting stock optimization in consecutive time periods”](https://www.sciencedirect.com/science/article/abs/pii/S037722170600213X)

## A threshold difference that can be checked by hand

Start with two 1,000 mm ash rails, then request one 797 mm piece followed by one 197 mm piece. Charge 3 mm kerf per cut. The first piece leaves exactly 200 mm.

| Threshold | Material used for the second order | Fresh rails across both orders | Cumulative irreversible loss |
| --- | --- | ---: | ---: |
| 200 mm | The 200 mm tail, used in full | 1 | 6 mm of kerf |
| 201 mm | The second 1,000 mm rail, leaving 800 mm | 2 | 6 mm of kerf + 200 mm discarded |

Both policies produce 994 mm of finished material. Swapping policy order or repeating the experiment returns the same results for each threshold. Removing the spare rail makes the 201 mm policy infeasible on the second order. The UI can show the completed first stage, and the result withholds a two-order total for the incomplete branch.

## A case where knowing the next order saves one full rail

Start with one 700 mm maple remnant and two fresh 1,000 mm maple rails. Keep tails of at least 200 mm. Order one needs a 397 mm piece. Order two needs 697 mm and 597 mm. With kerf, these pieces consume 400, 700 and 600 mm.

| Planning horizon | First order | Second order | Fresh rails | Loss |
| --- | --- | --- | ---: | ---: |
| Each order separately | Cut the 700 mm remnant and retain 300 mm | Open two fresh rails | 2 | 9 mm |
| Both orders together | Open a 1,000 mm rail and retain 600 mm | Use the untouched 700 mm remnant and the 600 mm tail | 1 | 9 mm |

The first decision in the sequential replay is uniquely best for its immediate fresh-rail objective. Both stages report an optimal plan for the rack they receive. At least one fresh rail is necessary across the horizon because the three gross demands total 1,700 mm and the starting remnant provides 700 mm. The second row attains this lower bound.

## Independent enumeration and observed results

```console
python tools/horizon_check.py
python tools/horizon_check.py --corpus
python -m unittest discover -s tests -p test_replay.py -v
```

The offline reference enumerates every assignment of labelled pieces to compatible rails for order one. For each feasible outcome it computes the residual rack and enumerates every second-order assignment. It adds the two orders' fresh-rail counts, loss and bar-use counts, selecting the smallest lexicographic score. A reused tail counts as another bar use in the second period while retaining its remnant classification. The exhaustive calculation shares no planner, proof or replay code. The comparison command calls the real replay separately.

On the maple example it examined three feasible first assignments and ten feasible complete assignment pairs. The sequential score was (2, 9, 3) and the joint score was (1, 9, 3). Physical rails A and B are distinct even when their lengths match.

A second run used seed 209 across 48 synthetic variations in starting remnant length, three piece lengths and retention threshold. The sequential and joint scores matched on 31 instances. Looking ahead improved the compound score on 16. One instance was infeasible for both. The reference accepts at most five initial rails and six finished pieces across two orders. These counts characterize this generator and the shipped planner.

Five automated replay tests verify threshold accounting, branch isolation, incomplete second orders, the maple counterexample and the oracle's treatment of incompatible materials.
