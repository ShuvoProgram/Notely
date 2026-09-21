import { Activity, Bell, CheckSquare, Home, Plug, type LucideIcon, NotebookPen, Settings, ShieldCheck, Sparkles, UserRound } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  /** Shorter label for the phone bottom bar. */
  short?: string;
  icon: LucideIcon;
  /** Match nested routes (e.g. /app/settings/*) */
  prefix?: boolean;
}

/**
 * Primary navigation: the four places people work, plus Settings. Search lives in the top bar
 * (⌘K) and integrations live under Settings → Connections, so neither is a sidebar entry.
 */
export const primaryNav: NavItem[] = [
  { href: "/app", label: "Home", icon: Home },
  { href: "/app/notes", label: "Notes", icon: NotebookPen, prefix: true },
  { href: "/app/tasks", label: "Tasks", icon: CheckSquare, prefix: true },
  { href: "/app/ai", label: "AI Assistant", short: "AI", icon: Sparkles },
  { href: "/app/settings", label: "Settings", icon: Settings, prefix: true },
];

export const settingsNav: NavItem[] = [
  { href: "/app/settings/profile", label: "Account", icon: UserRound },
  { href: "/app/settings/ai", label: "AI", icon: Sparkles },
  { href: "/app/settings/notifications", label: "Notifications", icon: Bell },
  { href: "/app/settings/connections", label: "Connections", icon: Plug, prefix: true },
  { href: "/app/settings/security", label: "Security", icon: ShieldCheck },
  { href: "/app/settings/activity", label: "Activity", icon: Activity },
];

export function isActive(pathname: string, item: NavItem, siblings: NavItem[] = []): boolean {
  const matches = (i: NavItem) => (i.prefix ? pathname === i.href || pathname.startsWith(`${i.href}/`) : pathname === i.href);
  if (!matches(item)) return false;
  // When several prefix items match, only the most specific one is active.
  return !siblings.some((s) => s !== item && matches(s) && s.href.length > item.href.length);
}

export const navSets = { primary: primaryNav, settings: settingsNav } as const;
export type NavSet = keyof typeof navSets;
