"""Create the first admin login account.

Usage:
    python scripts/seed_admin.py <username> [password]

If the password is omitted you are prompted for it, with the input hidden, so
it does not end up in a shell history or a process listing. Idempotent: an
existing user has their password reset and their role raised to admin.

This account is break-glass. Once it exists, the sensible way to administer the
app is an Entra security group set in Settings — see ``AppConfig.admin_group_id``
— and this account is the one you use to configure that.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

# Running this as a script ("python scripts/seed_admin.py") puts scripts/ on
# sys.path, not the repo root, so the app's own packages are not importable.
# Add the root explicitly rather than requiring the reader to know to type
# "python -m scripts.seed_admin" — the README tells them the plain form.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from shared.db import SessionLocal
from shared.migrate import upgrade_to_head
from shared.models import AppUser
from shared.security import hash_password


async def seed(username: str, password: str) -> str:
    """Create or update the account. Returns what happened, for the caller."""
    async with SessionLocal() as session:
        existing = await session.scalar(
            select(AppUser).where(AppUser.username == username)
        )
        if existing:
            existing.password_hash = hash_password(password)
            existing.role = "admin"
            outcome = f"Updated existing user '{username}' as admin."
        else:
            session.add(
                AppUser(
                    username=username,
                    password_hash=hash_password(password),
                    role="admin",
                )
            )
            outcome = f"Created admin user '{username}'."
        await session.commit()
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the first admin account.")
    parser.add_argument("username")
    parser.add_argument(
        "password",
        nargs="?",
        help="Omit to be prompted, which keeps it out of your shell history.",
    )
    args = parser.parse_args()

    password = args.password or getpass.getpass("Admin password: ")
    if not password:
        print("Password cannot be empty.", file=sys.stderr)
        return 1

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Only the CLI migrates: Alembic is synchronous and must not be called from
    # inside a running event loop, so it happens here rather than in seed().
    upgrade_to_head()
    print(asyncio.run(seed(args.username, password)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
