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

/**
 * Primary / settings navigation. Vertical: a soft glass pill with a green indicator for the
 * active item. Horizontal (phone bottom bar): icon-over-label, the active item lifted onto a pill.
 */
export function SidebarNav({ nav, orientation = "vertical", onNavigate, className }: SidebarNavProps) {
  const pathname = usePathname();
  const items = navSets[nav];
  const phone = orientation === "horizontal";
  const visible = items;
  return (
    <ul className={cn(phone ? "grid auto-cols-fr grid-flow-col" : "flex flex-col gap-0.5", className)}>
      {visible.map((item) => {
        const active = isActive(pathname, item, items);
        const Icon = item.icon;
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "group relative flex items-center gap-3 rounded-xl text-sm font-medium outline-none transition-[background-color,color,transform] duration-200 ease-out focus-visible:ring-2 focus-visible:ring-ring",
                phone ? "flex-col gap-1 px-1 py-1.5 text-[11px]" : "px-3 py-2",
                active
                  ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-1"
                  : "text-sidebar-foreground/70 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
              )}
            >
              {!phone ? (
                <span
                  aria-hidden
                  className={cn(
                    "absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-ai transition-opacity duration-200",
                    active ? "opacity-100" : "opacity-0",
                  )}
                />
              ) : null}
              <span
                className={cn(
                  "grid place-items-center rounded-lg transition-colors",
                  phone ? "size-8" : "size-6",
                  active && phone ? "bg-ai-soft text-ai" : "",
                )}
              >
                <Icon className={cn("shrink-0", phone ? "size-[18px]" : "size-4", active && !phone && "text-ai")} aria-hidden />
              </span>
              <span className="truncate">{phone ? (item.short ?? item.label) : item.label}</span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
