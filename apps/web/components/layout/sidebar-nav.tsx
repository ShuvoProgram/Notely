"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { isActive, navSets, type NavSet } from "@/lib/navigation";
import { cn } from "@/lib/utils";

interface SidebarNavProps {
  /** Which nav set to render. Resolved client-side so server layouts pass only serialisable props. */
  nav: NavSet;
  orientation?: "vertical" | "horizontal";
  onNavigate?: () => void;
  className?: string;
}

export function SidebarNav({ nav, orientation = "vertical", onNavigate, className }: SidebarNavProps) {
  const pathname = usePathname();
  const items = navSets[nav];
  return (
    <ul
      className={cn(
        orientation === "vertical" ? "flex flex-col gap-1" : "grid auto-cols-fr grid-flow-col",
        className,
      )}
    >
      {items.map((item) => {
        const active = isActive(pathname, item, items);
        const Icon = item.icon;
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring",
                orientation === "vertical"
                  ? "px-3 py-2"
                  : "flex-col gap-1 px-2 py-2 text-[11px]",
                active
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/75 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
              )}
            >
              <Icon className={cn("shrink-0", orientation === "vertical" ? "size-4" : "size-5")} aria-hidden />
              <span>{item.label}</span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
