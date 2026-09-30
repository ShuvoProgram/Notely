"use client";

import Link from "next/link";
import * as React from "react";

import { ArrowLeft, ShieldCheck } from "@/components/icons";
import { Logo } from "@/components/brand/logo";
import { SidebarNav } from "@/components/layout/sidebar-nav";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { UserAvatar } from "@/components/layout/user-avatar";
import { Button } from "@/components/ui/button";
import { RoleBadge } from "@/features/admin/components/admin-ui";
import { AppBackdrop, AppearanceSync } from "@/lib/appearance/appearance-sync";
import type { User } from "@/lib/api/types";
import { adminNav, isActive } from "@/lib/navigation";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

/**
 * Admin console chrome. Same Notely glass, type and theme as the workspace, but its own
 * navigation and an unmistakable "Admin" marker, so nobody confuses the two.
 *
 *   phone  (<768)      header + a horizontally scrolling tab strip (seven places don't fit a bottom bar)
 *   tablet (768–1023)  icon rail
 *   desktop (≥1024)    full sidebar
 */
export function AdminShell({ user, children }: { user: User; children: React.ReactNode }) {
  return (
    <div className="flex h-dvh w-full overflow-hidden">
      <AppearanceSync initialUser={user} />
      <AppBackdrop />
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
      >
        Skip to content
      </a>

      <aside className="glass-nav hidden w-[5.5rem] shrink-0 flex-col border-y-0 border-l-0 md:flex lg:hidden" aria-label="Admin sidebar">
        <div className="flex h-16 shrink-0 items-center justify-center">
          <Link href="/admin" className="rounded-md focus-visible:outline-2" aria-label="Admin overview">
            <Logo compact />
          </Link>
        </div>
        <nav aria-label="Admin" className="scrollbar-thin flex-1 overflow-y-auto px-2 pb-4">
          <SidebarNav nav="admin" orientation="rail" />
        </nav>
      </aside>

      <aside className="glass-nav hidden w-60 shrink-0 flex-col border-y-0 border-l-0 lg:flex" aria-label="Admin sidebar">
        <div className="flex h-16 items-center gap-2 px-5">
          <Link href="/admin" className="rounded-md focus-visible:outline-2">
            <Logo />
          </Link>
          <AdminChip />
        </div>
        <nav aria-label="Admin" className="scrollbar-thin flex-1 overflow-y-auto px-3 pb-4">
          <SidebarNav nav="admin" />
        </nav>
        <div className="border-t border-glass-border p-3">
          <Button asChild variant="ghost" className="w-full justify-start">
            <Link href="/app">
              <ArrowLeft aria-hidden /> Back to workspace
            </Link>
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="glass-nav z-20 shrink-0 border-x-0 border-t-0">
          <div className="flex h-14 items-center gap-2 px-3 sm:px-5 md:h-16">
            <Link href="/admin" className="rounded-md md:hidden" aria-label="Admin overview">
              <Logo compact />
            </Link>
            <span className="md:hidden">
              <AdminChip />
            </span>
            <p className="hidden text-sm text-muted-foreground md:block lg:hidden">Notely Admin</p>
            <div className="ml-auto flex items-center gap-1.5">
              <Button asChild variant="ghost" size="sm" className="lg:hidden">
                <Link href="/app" aria-label="Back to workspace">
                  <ArrowLeft aria-hidden /> <span className="max-sm:hidden">Workspace</span>
                </Link>
              </Button>
              <ThemeToggle />
              <div className="flex items-center gap-2 pl-1">
                <UserAvatar name={user.display_name} src={user.avatar_url} />
                <div className="hidden min-w-0 flex-col leading-tight sm:flex">
                  <span className="max-w-40 truncate text-xs font-medium">{user.email}</span>
                  <RoleBadge role={user.role ?? "user"} />
                </div>
              </div>
            </div>
          </div>
          <PhoneTabs />
        </header>

        <main id="main" tabIndex={-1} className="scrollbar-thin flex-1 overflow-y-auto focus:outline-none">
          <div className="app-canvas mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 sm:py-8">{children}</div>
        </main>
      </div>
    </div>
  );
}

function AdminChip() {
  return (
    <span className="inline-flex h-6 items-center gap-1 rounded-full border border-warning/40 bg-warning/10 px-2 text-[11px] font-semibold uppercase tracking-wide text-warning">
      <ShieldCheck className="size-3.5" aria-hidden /> Admin
    </span>
  );
}

function PhoneTabs() {
  const pathname = usePathname();
  const ref = React.useRef<HTMLUListElement>(null);
  React.useEffect(() => {
    ref.current?.querySelector<HTMLElement>("[aria-current=page]")?.scrollIntoView({ inline: "center", block: "nearest" });
  }, [pathname]);
  return (
    <nav aria-label="Admin" className="md:hidden">
      <ul ref={ref} className="scrollbar-none flex gap-1 overflow-x-auto px-3 pb-2">
        {adminNav.map((item) => {
          const active = isActive(pathname, item, adminNav);
          const Icon = item.icon;
          return (
            <li key={item.href} className="shrink-0">
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  active ? "liquid-selected text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Icon className={cn("size-4", active && "text-ai")} aria-hidden />
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
