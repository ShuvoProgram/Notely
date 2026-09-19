"use client";

import { Menu } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Logo } from "@/components/brand/logo";
import { SidebarNav } from "@/components/layout/sidebar-nav";
import { UserMenu } from "@/components/layout/user-menu";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import type { User } from "@/lib/api/types";

/**
 * Desktop: fixed sidebar + workspace. Tablet: sidebar collapses into a sheet.
 * Mobile: bottom navigation. The main region is the only scroll container.
 */
export function AppShell({ user, children }: { user: User; children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);

  return (
    <div className="flex h-dvh w-full overflow-hidden bg-background">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
      >
        Skip to content
      </a>

      <aside className="hidden w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar lg:flex">
        <div className="flex h-14 items-center px-4">
          <Link href="/app" className="rounded-md focus-visible:outline-2">
            <Logo />
          </Link>
        </div>
        <nav aria-label="Primary" className="flex-1 overflow-y-auto px-3 py-2">
          <SidebarNav nav="primary" />
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b px-3 sm:px-4">
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="hidden md:inline-flex lg:hidden" aria-label="Open navigation">
                <Menu aria-hidden />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-64 bg-sidebar p-0">
              <SheetHeader className="h-14 justify-center border-b border-sidebar-border px-4">
                <SheetTitle asChild>
                  <Logo />
                </SheetTitle>
              </SheetHeader>
              <nav aria-label="Primary" className="px-3 py-2">
                <SidebarNav nav="primary" onNavigate={() => setOpen(false)} />
              </nav>
            </SheetContent>
          </Sheet>
          <Link href="/app" className="rounded-md lg:hidden">
            <Logo compact />
          </Link>
          <div className="ml-auto flex items-center gap-1">
            <UserMenu initialUser={user} />
          </div>
        </header>

        <main id="main" tabIndex={-1} className="flex-1 overflow-y-auto pb-20 focus:outline-none md:pb-0">
          <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 sm:py-8">{children}</div>
        </main>

        <nav
          aria-label="Primary"
          className="fixed inset-x-0 bottom-0 border-t border-sidebar-border bg-sidebar/95 backdrop-blur supports-[backdrop-filter]:bg-sidebar/80 md:hidden"
          style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
        >
          <SidebarNav nav="primary" orientation="horizontal" className="px-2 py-1" />
        </nav>
      </div>
    </div>
  );
}
