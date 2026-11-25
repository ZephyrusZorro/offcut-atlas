"""Durable worker. A claim token fences late writers after a restart."""
import logging
import sqlite3
import threading
from .proof import verify
from .solver import solve

LOG = logging.getLogger("atlas.worker")


def process_one(ledger):
    job = ledger.claim()
    if not job:
        return False
    key, token, req, stock = job
    try:
        result = solve(stock, req["parts"], req["kerf_mm"], req["reuse_mm"])
        proof = None
        status = result["status"]
        if status in ("optimal", "feasible"):
            proof = verify(stock, req["parts"], req["kerf_mm"], req["reuse_mm"], result)
            if not proof["valid"]:
                ledger.finish(key, token, "failed", result, proof, "Independent verification rejected the allocation.")
                return True
        ledger.finish(key, token, status, result, proof)
    except Exception:
        LOG.exception("planning_failed run=%s", key)
        ledger.finish(key, token, "failed", error="Planner failed. The inventory snapshot is preserved.")
    return True


class Worker(threading.Thread):
    def __init__(self, ledger):
        super().__init__(name="offcut-worker", daemon=True)
        self.ledger = ledger
        self.stopped = threading.Event()
        self.wake = threading.Event()

    def run(self):
        while not self.stopped.is_set():
            self.wake.clear()
            try:
                if process_one(self.ledger):
                    continue
            except sqlite3.Error:
                LOG.exception("ledger_temporarily_unavailable")
            self.wake.wait(1.0)

    def close(self):
        self.stopped.set()
        self.wake.set()
        self.join(timeout=10)
