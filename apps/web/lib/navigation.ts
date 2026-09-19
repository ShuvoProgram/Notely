import { Home, type LucideIcon, NotebookPen, Search, Settings, ShieldCheck, UserRound } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Match nested routes (e.g. /app/settings/*) */
  prefix?: boolean;
}

/**
 * Primary navigation. Phase 2+ adds Notes, Search, Tasks, AI Assistant and Connections here;
 * items are only listed once their routes exist so the shell never links to dead ends.
 */
export const primaryNav: NavItem[] = [
  { href: "/app", label: "Home", icon: Home },
  { href: "/app/notes", label: "Notes", icon: NotebookPen, prefix: true },
  { href: "/app/search", label: "Search", icon: Search },
  { href: "/app/settings", label: "Settings", icon: Settings, prefix: true },
];

export const settingsNav: NavItem[] = [
  { href: "/app/settings/profile", label: "Profile", icon: UserRound },
  { href: "/app/settings/security", label: "Security", icon: ShieldCheck },
];

export function isActive(pathname: string, item: NavItem): boolean {
  return item.prefix ? pathname === item.href || pathname.startsWith(`${item.href}/`) : pathname === item.href;
}

export const navSets = { primary: primaryNav, settings: settingsNav } as const;
export type NavSet = keyof typeof navSets;
