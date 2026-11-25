# Release verification

Executed on 25 November 2026 with CPython 3.12.9 on a Windows workstation. The native app, a fresh demo ledger and temporary test ledgers were exercised. All performance observations are local fixture measurements.

| Evidence | Result |
| --- | --- |
| Standard suite | 41 tests covering optimization, joint lookahead, independent accounting, ledger transactions, retry handling, HTTP contracts and replay. |
| Exhaustive references | The shipped single-order test compares against 160 small cases. A separate production lookahead test compares against 160 independently enumerated pairs. |
| Synthetic benchmark | 13 optimal, three node-limited feasible, one infeasible. Across the 16 paired feasible cases the objective improved 15 times and tied once. [Raw run](evidence/benchmark.json) |
| Two-period evaluation | 48 variations yielded 31 ties between sequential and globally best scores, 16 gains from joint planning and one infeasible case. [Method](replay-evaluation.md) |
| Browser | A fresh browser and disposable ledgers passed at both 1440 × 960 and 390 × 844. The suite also rendered an applied cut sheet to A4 PDF bytes, surfaced an interrupted network request, and retried an acknowledged stock delivery without creating duplicate rails. [Desktop](evidence/cutting-desk-1440.png) · [Mobile](evidence/cutting-desk-390.png) · [Joint allocation](evidence/two-order-lookahead.png) |
| Automated accessibility | axe-core 4.13.0 reported zero violations for the chosen WCAG 2 A/AA and 2.1 A/AA tags over eight sampled desktop states in Chromium. The harness enabled script injection for the audit. Manual screen-reader and device testing remain open. [Recorded violations per state](evidence/accessibility.json) |
| Portable evidence | The independent checker accepted the exported Northlight run. Tests change labels, cut lengths, totals and record structure and check rejection. [Example packet](evidence/northlight-packet.json) |
| Infrastructure | Native loopback service and SQLite backup/restore were exercised. Docker Compose configuration validated. The local Docker daemon was unavailable for image build or execution. The repository includes CI configuration for a future remote run. |

## Improvements found during evaluation

- A length-capacity bound eliminates a case where adequate total length hid a shortage of individually usable rails.
- Relocation and pair exchanges improved the dense-02 incumbent from 722 mm of loss to 173 mm at the same search budget. Alternative inventory ordering still beats the bounded solver on one further seed.
- The two-period exhaustive reference identified losses from myopic planning. Bounded joint search is available in the workbench and verifies each order before presenting a result.
- Receiving stock now binds a retry key to the original receipt. A browser test explicitly drops an acknowledgement after the server has committed the delivery.
- Material labels normalize Unicode composition on intake and when loading the rack. Existing equivalent stored names remain usable.
- Early HTTP rejection briefly drains unread bytes after sending the response. Repeated malformed input tests on Windows confirm that a readable HTTP error reaches the client.

A node-limited result establishes feasibility when the checker accepts it. The checker does not independently prove optimality for arbitrary orders. Its SHA-256 fingerprint protects comparison against a separately trusted digest. These checks establish local consistency under the stated material model.
