"use client";

import { LifeBuoy, LogOut, Settings, UserRound } from "@/components/icons";
import Link from "next/link";

import { UserAvatar } from "@/components/layout/user-avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useCurrentUser, useLogout } from "@/features/auth/hooks";
import { LEGAL } from "@/lib/legal";
import type { User } from "@/lib/api/types";

export { initialsOf } from "@/components/layout/user-avatar";

export function UserMenu({ initialUser }: { initialUser: User }) {
  const { data: user = initialUser } = useCurrentUser(initialUser);
  const logout = useLogout();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="rounded-full" aria-label="Account menu">
          <UserAvatar name={user.display_name} src={user.avatar_url} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="font-normal">
          <p className="truncate text-sm font-medium">{user.display_name}</p>
          <p className="truncate text-xs text-muted-foreground">{user.email}</p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/app/settings/profile">
            <UserRound aria-hidden /> Your account
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/app/settings">
            <Settings aria-hidden /> Settings
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <a href={`mailto:${LEGAL.contactEmail}?subject=Notely%20help`}>
            <LifeBuoy aria-hidden /> Help &amp; support
          </a>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => logout.mutate()} disabled={logout.isPending}>
          <LogOut aria-hidden /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
