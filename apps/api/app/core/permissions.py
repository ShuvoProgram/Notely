"""Platform (admin) permissions. The role comes from the database on every request; the
client never supplies it. See app.models.user.PlatformRole for what each role is for."""

from __future__ import annotations

import enum

from app.models.user import PlatformRole


class Permission(enum.StrEnum):
    read = "admin:read"  # every admin page and report
    manage_users = "users:manage"  # suspend, reactivate, sign a person out
    manage_roles = "roles:manage"  # grant or remove staff roles
    manage_platform = "platform:manage"  # platform settings, connector availability


ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    PlatformRole.user: frozenset(),
    PlatformRole.viewer: frozenset({Permission.read}),
    PlatformRole.support: frozenset({Permission.read, Permission.manage_users}),
    PlatformRole.admin: frozenset(Permission),
}

# Higher rank may act on lower rank only (support can't suspend an admin).
ROLE_RANK: dict[str, int] = {
    PlatformRole.user: 0,
    PlatformRole.viewer: 1,
    PlatformRole.support: 2,
    PlatformRole.admin: 3,
}


def permissions_for(role: str | None) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role or PlatformRole.user, frozenset())
