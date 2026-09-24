"use client";

import Link from "next/link";
import * as React from "react";

import { Logo } from "@/components/brand/logo";
import { CommandPalette } from "@/components/layout/command-palette";
import { SidebarNav } from "@/components/layout/sidebar-nav";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { UserMenu } from "@/components/layout/user-menu";
import { FolderSidebar } from "@/features/folders/components/folder-sidebar";
import { NotificationBell } from "@/features/notifications/components/notification-bell";
import { AppBackdrop, AppearanceSync } from "@/lib/appearance/appearance-sync";
import { SfxPreferenceSync } from "@/lib/sfx/sfx-preference-sync";
import type { User } from "@/lib/api/types";

/**
 * Application chrome. Exactly one primary navigation exists at each width:
 *
 *   phone  (<768)      glass bottom bar: Home, Notes, Tasks, AI, Automations (thumb reach);
 *                      Settings sits in the account menu.
 *   tablet (768–1023)  slim icon rail: the same places plus Settings.
 *   desktop (≥1024)    full glass sidebar: primary nav plus folders and tags.
 *
 * Below desktop, folders and tags live where they belong, in Notes ("Folders & tags" opens a
 * bottom sheet), not in a navigation drawer. The main region is the only scroll container, so
 * panels inside screens can size themselves to the viewport.
 */
export function AppShell({ user, children }: { user: User; children: React.ReactNode }) {
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

      <aside className="glass-nav hidden w-[5.5rem] shrink-0 flex-col items-stretch border-y-0 border-l-0 md:flex lg:hidden" aria-label="Sidebar">
        <div className="flex h-16 shrink-0 items-center justify-center">
          <Link href="/app" className="rounded-md focus-visible:outline-2" aria-label="Home">
            <Logo compact />
          </Link>
        </div>
        <nav aria-label="Primary" className="scrollbar-thin flex-1 overflow-y-auto px-2 pb-4">
          <SidebarNav nav="primary" orientation="rail" />
        </nav>
      </aside>

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

        <main id="main" tabIndex={-1} className="scrollbar-thin flex-1 overflow-y-auto pb-[var(--mobile-nav-space)] focus:outline-none">
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
