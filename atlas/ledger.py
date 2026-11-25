"""SQLite owns the inventory, snapshots, persistent work queue and booking receipts."""
import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from . import demo
from .proof import verify
from .validation import Problem, demand, intake, material


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def uid(prefix):
    return f"{prefix}-{uuid4().hex}"


def event(db, run_id, stage, detail):
    db.execute("INSERT INTO events(run_id,stage,detail,created_at) VALUES(?,?,?,?)",
               (run_id, stage, detail, now()))


def available(db):
    return [{**dict(r), "material": material(r["material"])} for r in db.execute(
        "SELECT id,material,length_mm,kind,source_run,parent_id FROM rails WHERE consumed_by IS NULL ORDER BY material, id")]


def row_for(db, key):
    row = db.execute("SELECT * FROM runs WHERE id=?", (key,)).fetchone()
    if not row:
        raise Problem(404, "missing_run", "This run does not exist.")
    return row


def detail(db, row):
    item = dict(row)
    for field in ("request", "stocks", "result", "verification", "receipt"):
        item[field] = json.loads(item[field]) if item[field] else None
    for field in ("token", "lease_until", "request_key"):
        del item[field]
    item["committed"] = bool(item["receipt"])
    item["events"] = [dict(r) for r in db.execute(
        "SELECT * FROM events WHERE run_id=? ORDER BY id", (item["id"],))]
    return item


def enqueue(db, order, key=None):
    if key:
        previous = db.execute("SELECT * FROM runs WHERE request_key=?", (key,)).fetchone()
        if previous:
            if previous["request"] != encode(order):
                raise Problem(409, "key_conflict", "That request key already identifies a different order.")
            return previous["id"]
    if db.execute("SELECT count(*) FROM runs WHERE status IN ('queued','running')").fetchone()[0] >= 24:
        raise Problem(429, "queue_full", "The 24-job queue is full. Try again after a job completes.")
    run_id = uid("run")
    stocks = available(db)
    db.execute("""INSERT INTO runs(id,name,created_at,revision,request,stocks,status,request_key)
                  SELECT ?,?,?,revision,?,?,'queued',? FROM meta""",
               (run_id, order["name"], now(), encode(order), encode(stocks), key))
    event(db, run_id, "queued", f"Captured {len(stocks)} available rails in a fixed inventory snapshot.")
    return run_id


class Ledger:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def transaction(self, write=False):
        db = sqlite3.connect(self.path, timeout=8, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self, seed=True):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=8)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
        finally:
            connection.close()
        with self.transaction(write=True) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise RuntimeError("This database was created by a newer Offcut Atlas.")
            if version == 2:
                return
            if version == 0:
                schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
                for statement in schema.split(";"):
                    if statement.strip():
                        db.execute(statement)
                db.execute("INSERT INTO meta VALUES(1,?)", (int(seed),))
                if seed:
                    db.executemany("INSERT INTO rails(id,material,length_mm,kind) VALUES(?,?,?,?)", demo.RAILS)
                    event(db, None, "intake", "Loaded nine synthetic rails for the Northlight exhibition.")
                    enqueue(db, demo.ORDER)
            db.execute("""CREATE TABLE intakes (
                request_key TEXT PRIMARY KEY, request TEXT NOT NULL, receipt TEXT NOT NULL)""")
            db.execute("PRAGMA user_version=2")

    def add_stock(self, value, key=None):
        item = intake(value)
        with self.transaction(write=True) as db:
            if key:
                prior = db.execute("SELECT request,receipt FROM intakes WHERE request_key=?", (key,)).fetchone()
                if prior:
                    if prior["request"] != encode(item):
                        raise Problem(409, "key_conflict", "That key already identifies a different stock receipt.")
                    return json.loads(prior["receipt"])
            count = db.execute("SELECT count(*) FROM rails WHERE consumed_by IS NULL").fetchone()[0]
            if count + item["qty"] > 128:
                raise Problem(409, "rack_full", "This rack holds up to 128 available rails.")
            ids = [uid("rail") for _ in range(item["qty"])]
            db.executemany("INSERT INTO rails(id,material,length_mm,kind) VALUES(?,?,?,?)",
                           [(key, item["material"], item["length_mm"], item["kind"]) for key in ids])
            db.execute("UPDATE meta SET revision=revision+1")
            event(db, None, "intake", f"Received {len(ids)} × {item['length_mm']} mm {item['material']}.")
            receipt = {"ids": ids, "revision": db.execute("SELECT revision FROM meta").fetchone()[0]}
            if key:
                db.execute("INSERT INTO intakes VALUES(?,?,?)", (key, encode(item), encode(receipt)))
            return receipt

    def submit(self, value, key=None):
        order = demand(value)
        with self.transaction(write=True) as db:
            return enqueue(db, order, key)

    def run(self, run_id):
        with self.transaction() as db:
            return detail(db, row_for(db, run_id))

    def workspace(self):
        with self.transaction() as db:
            rows = db.execute("""SELECT id,name,created_at,status,revision,receipt IS NOT NULL AS committed
                                 FROM runs ORDER BY rowid DESC LIMIT 100""")
            runs = [{**dict(r), "committed": bool(r["committed"])} for r in rows]
            draft = json.loads(row_for(db, runs[0]["id"])["request"]) if runs else demo.ORDER
            return dict(revision=db.execute("SELECT revision FROM meta").fetchone()[0], stocks=available(db),
                        draft=draft, runs=runs,
                        events=[dict(r) for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 100")])

    def claim(self):
        with self.transaction(write=True) as db:
            row = db.execute("""SELECT * FROM runs WHERE status='queued'
                             OR (status='running' AND lease_until<=?) ORDER BY rowid LIMIT 1""",
                             (time.time(),)).fetchone()
            if not row:
                return None
            if row["attempts"] >= 4:
                db.execute("UPDATE runs SET status='failed',error=?,token=NULL,lease_until=NULL WHERE id=?",
                           ("Worker claim expired repeatedly. Submit a new plan.", row["id"]))
                event(db, row["id"], "failed", "Four interrupted attempts. Snapshot preserved.")
                return None
            token = uuid4().hex
            db.execute("UPDATE runs SET status='running',token=?,lease_until=?,attempts=attempts+1 WHERE id=?",
                       (token, time.time()+90, row["id"]))
            message = "Reclaimed interrupted work." if row["attempts"] else "Started bounded material allocation."
            event(db, row["id"], "planning", message)
            return row["id"], token, json.loads(row["request"]), json.loads(row["stocks"])

    def finish(self, run_id, token, status, result=None, verification=None, error=None):
        with self.transaction(write=True) as db:
            changed = db.execute("""UPDATE runs SET status=?,result=?,verification=?,error=?,token=NULL,lease_until=NULL
                                  WHERE id=? AND status='running' AND token=?""",
                                 (status, encode(result) if result else None, encode(verification) if verification else None,
                                  error, run_id, token)).rowcount
            if changed:
                if result:
                    event(db, run_id, "search", f"{result['status'].capitalize()} after {result['nodes']} search nodes.")
                if verification:
                    verdict = "passed" if verification["valid"] else "failed"
                    event(db, run_id, "verification", f"Independent material accounting {verdict}.")
                event(db, run_id, status, error or (result or {}).get("message", "Finished."))
            return bool(changed)

    def commit(self, run_id):
        with self.transaction(write=True) as db:
            run = detail(db, row_for(db, run_id))
            if run["committed"]:
                return run["receipt"]
            if run["status"] not in ("optimal", "feasible"):
                raise Problem(409, "unbookable", "Only a verified feasible allocation can be booked.")
            req, result = run["request"], run["result"]
            proof = verify(run["stocks"], req["parts"], req["kerf_mm"], req["reuse_mm"], result)
            if not proof["valid"] or proof["digest"] != (run["verification"] or {}).get("digest"):
                raise Problem(409, "invalid_proof", "The saved allocation failed independent verification.")
            created, used = [], []
            for bar in result["bars"]:
                parent = bar["stock_id"]
                changed = db.execute("UPDATE rails SET consumed_by=? WHERE id=? AND consumed_by IS NULL",
                                     (run_id, parent)).rowcount
                if changed != 1:
                    raise Problem(409, "stock_conflict", f"Rail {parent} has already been booked. Plan again with current stock.")
                used.append(parent)
                if bar["tail_mm"] >= req["reuse_mm"]:
                    key = uid("tail")
                    db.execute("""INSERT INTO rails(id,material,length_mm,kind,source_run,parent_id)
                                  SELECT ?,material,?,'remnant',?,id FROM rails WHERE id=?""",
                               (key, bar["tail_mm"], run_id, parent))
                    created.append(dict(id=key, parent_id=parent, length_mm=bar["tail_mm"]))
            db.execute("UPDATE meta SET revision=revision+1")
            receipt = dict(run_id=run_id, committed_at=now(), consumed=used, returned=created,
                           revision=db.execute("SELECT revision FROM meta").fetchone()[0], digest=proof["digest"])
            db.execute("UPDATE runs SET receipt=? WHERE id=?", (encode(receipt), run_id))
            event(db, run_id, "committed", f"Booked {len(used)} rails and issued {len(created)} reusable tails.")
            return receipt

    def packet(self, run_id):
        run = self.run(run_id)
        if not (run["verification"] or {}).get("valid"):
            raise Problem(409, "no_certificate", "This run has no verified allocation to export.")
        return dict(format="offcut-atlas/1", run_id=run_id, **{k: run[k] for k in
                    ("stocks", "request", "result", "verification", "receipt")})
