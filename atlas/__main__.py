"""Local launch and online SQLite backup."""
import argparse
import logging
import os
import sqlite3
from pathlib import Path

from .ledger import Ledger
from .server import Server
from .worker import Worker


def main():
    parser = argparse.ArgumentParser(prog="python -m atlas")
    sub = parser.add_subparsers(dest="action", required=True)
    serve = sub.add_parser("serve", help="Serve the workbench")
    serve.add_argument("--port", type=int, default=8764)
    serve.add_argument("--bind", choices=("127.0.0.1", "0.0.0.0"), default="127.0.0.1",
                       help="Use 0.0.0.0 only inside a container with loopback-only port publication.")
    serve.add_argument("--empty", action="store_true", help="Skip demonstration inventory on a new database")
    save = sub.add_parser("backup", help="Save a consistent SQLite snapshot")
    save.add_argument("output", type=Path)
    for cmd in (serve, save):
        cmd.add_argument("--db", type=Path, default=Path("var/studio.sqlite3"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.action == "backup":
        if not args.db.is_file():
            parser.error("Source database does not exist.")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            parser.error("Choose a new backup filename.")
        os.close(fd)
        source = sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True)
        target = sqlite3.connect(args.output)
        try:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup failed SQLite integrity check")
        finally:
            target.close()
            source.close()
        print(args.output.resolve())
        return
    if not 1 <= args.port <= 65535:
        parser.error("Port must be from 1 to 65535.")
    ledger = Ledger(args.db)
    ledger.initialize(seed=not args.empty)
    worker = Worker(ledger)
    with Server((args.bind, args.port), ledger, worker) as server:
        worker.start()
        print(f"Offcut Atlas • http://127.0.0.1:{server.server_port} • {ledger.path.resolve()}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            worker.close()


if __name__ == "__main__":
    main()
