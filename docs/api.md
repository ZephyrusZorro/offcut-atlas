# Local HTTP API v1

Base URL for a default launch is `http://127.0.0.1:8764/api/v1`. Requests and responses use UTF-8 JSON. Error objects contain `code` and a human-readable `error`. Supply a same-origin request or a local HTTP client. Use one `Content-Length` and `Content-Type: application/json` for writes. Maximum body size is 64 KiB.

| Method and path | Request | Response |
| --- | --- | --- |
| GET /health | — | Service status, schema version and worker thread liveness |
| GET /workspace | — | Revision, available stock, last draft, up to 100 recent runs and 100 recent events |
| POST /stock | Stock receipt | 201, new physical IDs and revision |
| POST /runs | Order | 202, run ID and Location header |
| GET /runs/{id} | — | Original request and stock snapshot, status, result, verification, receipt, ordered run events |
| POST /runs/{id}/commit | Empty JSON object | 200, booking receipt or 409 on overlapping stock |
| GET /runs/{id}/packet | — | Downloadable versioned JSON with snapshot, request, result, proof and optional booking receipt |
| POST /runs/{id}/replay | Two thresholds and following order | Two complete or partial verified sequential simulations |
| POST /runs/{id}/lookahead | One threshold and following order | Comparison of sequential and jointly planned orders |
| GET /experiments/lookahead | — | Live computation of the small maple teaching example |

The stock and run creation endpoints accept an optional `Idempotency-Key` of 1–96 ASCII letters, digits, underscores, dots or dashes. Repeating the same normalized payload and key returns the original resource. Reusing the key for a different payload returns 409. Intake and run keys have independent namespaces. The commit is naturally idempotent by run ID.

## Order

```json
{
  "name": "Gallery study",
  "parts": [{"id":"P1","label":"Long side","material":"Natural oak","length_mm":620,"qty":3}],
  "kerf_mm": 3,
  "reuse_mm": 300
}
```

An order supports 1–48 lines and 1–96 pieces total, kerf 0–20 mm and retention threshold 1–10,000 mm. Lengths range from 1–100,000 mm. IDs are unique within the order. Material names match case-sensitively and normalize to Unicode NFC. Unknown materials are valid planning inputs and can yield infeasibility. Give incompatible profiles distinct names.

## Stock receipt

```json
{"material":"Natural oak","length_mm":3100,"kind":"stock","qty":2}
```

Kind is `stock` or `remnant`. Intake quantity is 1–32. The rack supports 128 available rails. Every open stock item has a unique ID. Material, length and type are immutable.

## Planning and experiments

Poll the run resource until it leaves `queued` or `running`. The solver emits `optimal`, `feasible`, `infeasible` or `unknown`. Application-level `failed` records a worker or verification failure. Only verified feasible and optimal results can be booked. A blank inventory yields an inspectable shortage. Inventory revisions describe snapshots. Later inventory changes permit booking whenever all the selected physical rails are still available.

Replay accepts `{"threshold_a":300,"threshold_b":850,"next_order":<order>}`. Lookahead accepts `{"threshold_mm":300,"next_order":<order>}`. Replace the placeholder with a full order object. The experiment threshold overrides both input orders' retention settings. Each order retains its own kerf. The sequential simulator budgets 4,000 search nodes per order. Joint search supports seven relevant rails and ten total pieces with a 20,000-node budget plus two bounded incumbent calculations. Experiment responses do not reserve physical inventory.

Input failures produce 400 or 422. Oversized bodies produce 413. Unsupported content types produce 415. Disallowed hosts and browser origins produce 403. Missing resources produce 404. Conflicts produce 409. A full queue or competing user-run simulations produce 429. A storage availability error can produce 503. An unchanged request with a retry key can be retried after a lost reply.
