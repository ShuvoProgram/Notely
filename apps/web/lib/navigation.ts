import { Activity, Bell, CheckSquare, History, Home, LayoutGrid, Plug, type IconComponent, NotebookPen, Palette, Settings, Settings2, ShieldCheck, Sparkles, UserRound, Users, Workflow } from "@/components/icons";

export interface NavItem {
  href: string;
  label: string;
  /** Shorter label for the phone bottom bar. */
  short?: string;
  icon: IconComponent;
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
  { href: "/app/automations", label: "Automations", short: "Automate", icon: Workflow, prefix: true },
  { href: "/app/settings", label: "Settings", icon: Settings, prefix: true },
];

/**
 * The phone bottom bar: the five places people work. Six items don't fit a 320px screen without
 * shrinking labels until they're unreadable, so Settings lives in the account menu there instead.
 */
export const phoneNav: NavItem[] = primaryNav.filter((i) => i.href !== "/app/settings");

export const settingsNav: NavItem[] = [
  { href: "/app/settings/profile", label: "Account", icon: UserRound },
  { href: "/app/settings/ai", label: "AI", icon: Sparkles, prefix: true },
  { href: "/app/settings/appearance", label: "Appearance", icon: Palette },
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

/** Admin console (/admin). Separate from the workspace nav; every page is authorized by the API. */
export const adminNav: NavItem[] = [
  { href: "/admin", label: "Overview", icon: LayoutGrid },
  { href: "/admin/users", label: "Users", icon: Users, prefix: true },
  { href: "/admin/automations", label: "Automations", icon: Workflow, prefix: true },
  { href: "/admin/connectors", label: "Connectors", icon: Plug, prefix: true },
  { href: "/admin/ai", label: "AI usage", icon: Sparkles },
  { href: "/admin/audit", label: "Audit log", icon: History },
  { href: "/admin/settings", label: "Settings", icon: Settings2 },
];

export const navSets = { primary: primaryNav, phone: phoneNav, settings: settingsNav, admin: adminNav } as const;
export type NavSet = keyof typeof navSets;
