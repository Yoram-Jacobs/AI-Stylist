"""CLI fallback for promoting / demoting an admin user.

Use this when you need a one-off promotion without redeploying the backend
to update ``ADMIN_EMAILS``.

Usage:
    # promote
    python -m scripts.grant_admin you@example.com

    # demote
    python -m scripts.grant_admin you@example.com --revoke

    # list current admins
    python -m scripts.grant_admin --list
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make the backend package importable when this script is run directly.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load env BEFORE importing app modules so MONGO_URL etc. resolve.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

# Validate basics early to give a useful error.
if not os.environ.get("MONGO_URL"):
    print("ERROR: MONGO_URL not set in /app/backend/.env", file=sys.stderr)
    sys.exit(2)

from app.db.database import get_db, get_client  # noqa: E402


async def _promote(email: str) -> int:
    db = get_db()
    user = await db.users.find_one({"email": email.lower()}, {"_id": 0})
    if not user:
        print(f"No user found with email={email}", file=sys.stderr)
        return 1
    roles = list(user.get("roles") or [])
    if "user" not in roles:
        roles.append("user")
    if "admin" in roles:
        print(f"OK — {email} is already an admin (roles={roles})")
        return 0
    roles.append("admin")
    await db.users.update_one(
        {"id": user["id"]},
        {
            "$set": {
                "roles": roles,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    print(f"Promoted {email} → roles={roles}")
    return 0


async def _revoke(email: str) -> int:
    db = get_db()
    user = await db.users.find_one({"email": email.lower()}, {"_id": 0})
    if not user:
        print(f"No user found with email={email}", file=sys.stderr)
        return 1
    roles = [r for r in (user.get("roles") or []) if r != "admin"]
    if not roles:
        roles = ["user"]
    await db.users.update_one(
        {"id": user["id"]},
        {
            "$set": {
                "roles": roles,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    print(f"Revoked admin from {email} → roles={roles}")
    return 0


async def _list() -> int:
    db = get_db()
    cursor = db.users.find({"roles": "admin"}, {"_id": 0, "email": 1, "roles": 1, "id": 1})
    found = False
    async for u in cursor:
        found = True
        print(f"  {u.get('email'):40s}  roles={u.get('roles')}  id={u.get('id')}")
    if not found:
        print("(no admins yet)")
    return 0


async def _amain() -> int:
    parser = argparse.ArgumentParser(description="Manage admin role on DressApp users.")
    parser.add_argument("email", nargs="?", help="User email to promote / demote")
    parser.add_argument(
        "--revoke", action="store_true", help="Remove the admin role instead of granting"
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_admins", help="List current admins"
    )
    args = parser.parse_args()

    if args.list_admins:
        return await _list()
    if not args.email:
        parser.error("email is required (or pass --list)")
    return await _revoke(args.email) if args.revoke else await _promote(args.email)


def main() -> None:
    try:
        rc = asyncio.run(_amain())
    finally:
        # Make sure motor connections drain cleanly.
        try:
            get_client().close()
        except Exception:  # noqa: BLE001
            pass
    sys.exit(rc)


if __name__ == "__main__":
    main()
