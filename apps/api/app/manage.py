"""Operator commands that must not depend on an existing admin.

    uv run python -m app.manage set-role owner@example.com admin
    uv run python -m app.manage list-staff

Granting the first admin happens here, on the server, never through a sign-up or env var that
a stranger could race. Every change is written to the admin audit log (actor: "cli").
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.db.base import utcnow
from app.db.session import dispose_engine, get_session_factory
from app.models.admin import AdminAuditEvent
from app.models.user import STAFF_ROLES, PlatformRole, User


async def set_role(email: str, role: str) -> int:
    async with get_session_factory()() as db:
        user = await db.scalar(select(User).where(User.email == email.lower().strip()))
        if user is None:
            print(f"No account with email {email!r}.", file=sys.stderr)
            return 1
        previous = user.role
        user.role = PlatformRole(role).value
        db.add(
            AdminAuditEvent(
                actor_id=None,
                actor_email="cli",
                actor_role="operator",
                action="user.role_change",
                resource_type="user",
                resource_id=str(user.id),
                resource_label=user.email,
                result="success",
                metadata_={"from": previous, "to": user.role, "via": "cli"},
                created_at=utcnow(),
            )
        )
        await db.commit()
        print(f"{user.email}: {previous} -> {user.role}")
        return 0


async def list_staff() -> int:
    async with get_session_factory()() as db:
        rows = await db.scalars(
            select(User).where(User.role.in_([r.value for r in STAFF_ROLES])).order_by(User.email)
        )
        for user in rows:
            print(f"{user.role:8} {user.email}{'' if user.is_active else '  (suspended)'}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.manage")
    sub = parser.add_subparsers(dest="command", required=True)
    grant = sub.add_parser("set-role", help="Set an account's platform role")
    grant.add_argument("email")
    grant.add_argument("role", choices=[r.value for r in PlatformRole])
    sub.add_parser("list-staff", help="List accounts with an admin role")
    args = parser.parse_args()

    async def run() -> int:
        try:
            if args.command == "set-role":
                return await set_role(args.email, args.role)
            return await list_staff()
        finally:
            await dispose_engine()

    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
