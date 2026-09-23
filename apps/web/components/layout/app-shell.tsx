"use client";

import { Menu } from "@/components/icons";
import Link from "next/link";
import * as React from "react";

import { Logo } from "@/components/brand/logo";
import { CommandPalette } from "@/components/layout/command-palette";
import { SidebarNav } from "@/components/layout/sidebar-nav";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { UserMenu } from "@/components/layout/user-menu";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { FolderSidebar } from "@/features/folders/components/folder-sidebar";
import { NotificationBell } from "@/features/notifications/components/notification-bell";
import { AppBackdrop, AppearanceSync } from "@/lib/appearance/appearance-sync";
import { SfxPreferenceSync } from "@/lib/sfx/sfx-preference-sync";
import type { User } from "@/lib/api/types";

/**
 * Application chrome. Desktop: a glass sidebar (brand, primary nav, folders) beside a
 * workspace with a slim top bar (⌘K, theme, account). Tablet: the sidebar folds into a sheet.
 * Phone: a glass bottom bar carries the primary nav. The main region is the only scroll
 * container, so panels inside screens can size themselves to the viewport.
 */
export function AppShell({ user, children }: { user: User; children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);

  return (
    <div className="flex h-dvh w-full overflow-hidden">
      <SfxPreferenceSync initialUser={user} />
      <AppearanceSync initialUser={user} />
      <AppBackdrop />
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
      >
        Skip to content
      </a>

      <aside className="glass-nav hidden w-64 shrink-0 flex-col border-y-0 border-l-0 lg:flex" aria-label="Sidebar">
        <div className="flex h-16 items-center px-5">
          <Link href="/app" className="rounded-md focus-visible:outline-2">
            <Logo />
          </Link>
        </div>
        <div className="scrollbar-thin flex-1 overflow-y-auto px-3 pb-4">
          <nav aria-label="Primary">
            <SidebarNav nav="primary" />
          </nav>
          <div className="mt-6">
            <React.Suspense>
              <FolderSidebar />
            </React.Suspense>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Phones: every header control is at least 40px square, a comfortable thumb target. */}
        <header className="glass-nav z-20 flex h-16 shrink-0 items-center gap-1.5 border-x-0 border-t-0 px-3 max-md:[&_button]:min-h-10 max-md:[&_button]:min-w-10 sm:gap-2 sm:px-5">
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation">
                <Menu aria-hidden />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72 p-0">
              <SheetHeader className="h-16 justify-center px-5">
                <SheetTitle asChild>
                  <Logo />
                </SheetTitle>
              </SheetHeader>
              <div className="scrollbar-thin overflow-y-auto px-3 pb-6">
                <nav aria-label="Primary">
                  <SidebarNav nav="primary" onNavigate={() => setOpen(false)} />
                </nav>
                <div className="mt-6">
                  <React.Suspense>
                    <FolderSidebar onNavigate={() => setOpen(false)} />
                  </React.Suspense>
                </div>
              </div>
            </SheetContent>
          </Sheet>
          <Link href="/app" className="rounded-md md:hidden" aria-label="Home">
            <Logo compact />
          </Link>
          <div className="mx-auto flex w-full max-w-md justify-end sm:justify-center">
            <CommandPalette />
          </div>
          <div className="flex items-center gap-1">
            <NotificationBell />
            <ThemeToggle />
            <UserMenu initialUser={user} />
          </div>
        </header>

        <main id="main" tabIndex={-1} className="scrollbar-thin flex-1 overflow-y-auto pb-[calc(6rem+env(safe-area-inset-bottom))] focus:outline-none md:pb-0">
          <div className="app-canvas mx-auto w-full max-w-6xl px-4 py-6 has-[[data-full-bleed]]:max-w-none has-[[data-full-bleed]]:p-0 sm:px-6 sm:py-8">{children}</div>
        </main>

        {/* Phone bar: five equal columns that always fit, lifted clear of the home indicator. */}
        <nav
          aria-label="Primary"
          className="glass-2 fixed inset-x-[max(0.75rem,env(safe-area-inset-left))] bottom-[calc(0.75rem+env(safe-area-inset-bottom))] z-20 rounded-2xl md:hidden"
        >
          <SidebarNav nav="phone" orientation="horizontal" className="p-1" />
        </nav>
      </div>
    </div>
  );
}
