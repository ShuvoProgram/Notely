"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";

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
 * Primary / settings navigation. The active item sits on a single liquid pill that glides to the
 * new item on navigation (instead of one pill vanishing and another appearing), so moving around
 * the app reads as one continuous surface. Vertical: pill plus a small accent bar. Horizontal
 * (phone bottom bar): icon-over-label, the pill behind the active item.
 */
export function SidebarNav({ nav, orientation = "vertical", onNavigate, className }: SidebarNavProps) {
  const pathname = usePathname();
  const items = navSets[nav];
  const phone = orientation === "horizontal";
  const listRef = React.useRef<HTMLDivElement>(null);
  const pillRef = React.useRef<HTMLSpanElement>(null);
  const activeHref = items.find((item) => isActive(pathname, item, items))?.href ?? null;

  // Position the pill on the active link. Written straight to the element (no state, no re-render);
  // the first placement skips the transition so the pill doesn't fly in from the corner.
  React.useLayoutEffect(() => {
    const list = listRef.current;
    const pill = pillRef.current;
    if (!list || !pill) return;
    const place = () => {
      const link = activeHref ? list.querySelector<HTMLElement>(`a[href="${activeHref}"]`) : null;
      if (!link || link.offsetWidth === 0) {
        pill.style.opacity = "0";
        return;
      }
      pill.style.width = `${link.offsetWidth}px`;
      pill.style.height = `${link.offsetHeight}px`;
      pill.style.transform = `translate(${link.offsetLeft}px, ${link.offsetTop}px)`;
      pill.style.opacity = "1";
      if (!pill.dataset.ready) requestAnimationFrame(() => (pill.dataset.ready = "true"));
    };
    place();
    const observer = new ResizeObserver(place);
    observer.observe(list);
    return () => observer.disconnect();
  }, [activeHref]);

  return (
    <div ref={listRef} className="relative">
      <span
        ref={pillRef}
        aria-hidden
        className="liquid-selected pointer-events-none absolute left-0 top-0 rounded-xl opacity-0 data-[ready]:transition-[transform,width,height,opacity] data-[ready]:duration-300 data-[ready]:ease-liquid"
      >
        {!phone ? <span className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-ai" /> : null}
      </span>
      <ul className={cn(phone ? "grid auto-cols-[minmax(0,1fr)] grid-flow-col" : "flex flex-col gap-0.5", className)}>
      {items.map((item) => {
        const active = item.href === activeHref;
        const Icon = item.icon;
        return (
          <li key={item.href} className="min-w-0">
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "liquid-press group relative flex items-center gap-3 rounded-xl text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring",
                phone ? "min-h-14 flex-col justify-center gap-0.5 px-0.5 py-1.5 text-[11px] leading-tight" : "px-3 py-2",
                active ? "text-sidebar-accent-foreground" : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
              )}
            >
              <span className={cn("grid place-items-center rounded-lg transition-colors", phone ? "size-8" : "size-6", active && "text-ai")}>
                <Icon className={cn("shrink-0", phone ? "size-[18px]" : "size-4")} aria-hidden />
              </span>
              <span className={cn("truncate", phone && "max-w-full")}>{phone ? (item.short ?? item.label) : item.label}</span>
            </Link>
          </li>
        );
      })}
      </ul>
    </div>
  );
}
