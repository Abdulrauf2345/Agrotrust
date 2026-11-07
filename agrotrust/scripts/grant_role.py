#!/usr/bin/env python3
"""Grant a role to an already-registered user, directly in the database.

This exists because PLATFORM_ADMIN, LENDER, and FIELD_AGENT are deliberately NOT
self-registerable through the public /api/v1/auth/register endpoint (see
security/permissions.py's SELF_REGISTERABLE set) - that's a real privilege-escalation guard,
not an oversight. In a real deployment, an existing admin grants these roles through an admin
UI/endpoint; locally, this script does the equivalent for testing via Postman.

Usage:
    PYTHONPATH=src python3 scripts/grant_role.py --db .dev_data/agrotrust_dev.db \\
        --phone +2348011110099 --role PLATFORM_ADMIN

Must point at the SAME --db path you passed to run_dev_server.py.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from datetime import datetime, timezone  # noqa: E402

from agrotrust.db.database import Database  # noqa: E402
from agrotrust.shared.clock import to_iso  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="path to the running server's database file")
    parser.add_argument("--phone", required=True, help="the user's phone number, e.g. +2348011110099")
    parser.add_argument("--role", required=True,
                        help="role name, e.g. PLATFORM_ADMIN, LENDER, FIELD_AGENT, INSURER")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"No database found at {args.db} - is the server running with --db {args.db}?")
        raise SystemExit(1)

    db = Database(args.db)
    user = db.one("SELECT id, full_name FROM users WHERE phone=?", (args.phone,))
    if not user:
        print(f"No user found with phone {args.phone}. Register them first via POST /api/v1/auth/register.")
        raise SystemExit(1)

    with db.transaction():
        db.execute("INSERT INTO roles(name, self_register) VALUES (?, 0) ON CONFLICT(name) DO NOTHING", (args.role,))
        db.execute(
            "INSERT INTO user_roles(user_id, role, granted_at) VALUES (?, ?, ?)"
            " ON CONFLICT DO NOTHING", (user["id"], args.role, to_iso(datetime.now(timezone.utc))))

    print(f"Granted {args.role} to {user['full_name']} ({args.phone}, id={user['id']}).")
    print("They can now log in via POST /api/v1/auth/login and the token will carry this role.")
    db.close()


if __name__ == "__main__":
    main()
