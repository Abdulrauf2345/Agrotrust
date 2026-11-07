#!/usr/bin/env python3
"""Run the API locally against a FIXED database file (instead of a random temp file), so
other scripts (grant_role.py) and tools (Postman via the [DEV] endpoints) can reliably find
and talk to the same data the running server sees.

Usage:
    PYTHONPATH=src python3 scripts/run_dev_server.py
    PYTHONPATH=src python3 scripts/run_dev_server.py --db ./my_test.db --port 8080
    PYTHONPATH=src python3 scripts/run_dev_server.py --fresh   # delete the db file first

The database persists across restarts by default (so your Postman-created farms/orders/etc.
survive a server restart) - pass --fresh for a clean slate.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agrotrust.api.app import create_app  # noqa: E402
from agrotrust.api.container import Container  # noqa: E402

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", ".dev_data", "agrotrust_dev.db")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite file path (default: %(default)s)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--fresh", action="store_true", help="delete the database file before starting")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.db)), exist_ok=True)
    if args.fresh:
        for suffix in ("", "-wal", "-shm"):
            path = args.db + suffix
            if os.path.exists(path):
                os.remove(path)
        print(f"[run_dev_server] removed existing database at {args.db}")

    print(f"[run_dev_server] using database: {os.path.abspath(args.db)}")
    print(f"[run_dev_server] pass this same --db path to scripts/grant_role.py so they share state")
    container = Container(db_path=args.db)
    app = create_app(container)
    app.run(debug=True, port=args.port, use_reloader=False)
    # use_reloader=False: Flask's auto-reloader runs your script in a child process, which would
    # otherwise create a SECOND Container (and a confusing "why are my changes gone" moment).


if __name__ == "__main__":
    main()
