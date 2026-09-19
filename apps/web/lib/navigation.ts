import { Activity, CheckSquare, Home, Plug, type LucideIcon, NotebookPen, Search, Settings, ShieldCheck, Sparkles, UserRound } from "lucide-react";

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
  { href: "/app/tasks", label: "Tasks", icon: CheckSquare },
  { href: "/app/ai", label: "AI Assistant", icon: Sparkles },
  { href: "/app/settings/connections", label: "Connections", icon: Plug, prefix: true },
  { href: "/app/settings", label: "Settings", icon: Settings, prefix: true },
];

export const settingsNav: NavItem[] = [
  { href: "/app/settings/profile", label: "Profile", icon: UserRound },
  { href: "/app/settings/security", label: "Security", icon: ShieldCheck },
  { href: "/app/settings/ai", label: "AI", icon: Sparkles },
  { href: "/app/settings/connections", label: "Connections", icon: Plug, prefix: true },
  { href: "/app/settings/activity", label: "Activity", icon: Activity },
];

export function isActive(pathname: string, item: NavItem, siblings: NavItem[] = []): boolean {
  const matches = (i: NavItem) => (i.prefix ? pathname === i.href || pathname.startsWith(`${i.href}/`) : pathname === i.href);
  if (!matches(item)) return false;
  // When several prefix items match (e.g. /app/settings and /app/settings/connections), only the
  // most specific one is active.
  return !siblings.some((s) => s !== item && matches(s) && s.href.length > item.href.length);
}

export const navSets = { primary: primaryNav, settings: settingsNav } as const;
export type NavSet = keyof typeof navSets;
