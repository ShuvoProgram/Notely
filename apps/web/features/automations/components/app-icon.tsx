"use client";

import { Filter, GitBranch, NotebookPen, Sparkles } from "@/components/icons";

import { ProviderLogo } from "@/features/connections/components/marketplace";
import { cn } from "@/lib/utils";

import { appOf } from "../lib";
import type { Catalog } from "../types";

const SIZES = { xs: "size-5 rounded-md [&_svg]:size-3", sm: "size-8 rounded-lg [&_svg]:size-4", md: "size-10 rounded-xl [&_svg]:size-5" };

/** The app's logo, or a Notely-styled tile for built-ins (Notely, AI) and logic steps. */
export function AppIcon({
  appId,
  catalog,
  size = "sm",
  className,
}: {
  appId: string;
  catalog?: Catalog;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  const builtin =
    appId === "notely" ? { icon: NotebookPen, tone: "bg-primary/15 text-primary" }
    : appId === "ai" ? { icon: Sparkles, tone: "bg-ai-soft text-ai" }
    : appId === "filter" ? { icon: Filter, tone: "bg-warning/15 text-warning" }
    : appId === "branch" ? { icon: GitBranch, tone: "bg-info/15 text-info" }
    : null;
  if (builtin) {
    const Icon = builtin.icon;
    return (
      <span aria-hidden className={cn("grid shrink-0 place-items-center", SIZES[size], builtin.tone, className)}>
        <Icon />
      </span>
    );
  }
  const app = appOf(catalog, appId);
  return (
    <ProviderLogo
      provider={{ name: app?.name ?? appId, logo_url: app?.logo ?? null }}
      size={size === "md" ? "md" : "sm"}
      className={cn(size === "xs" && "size-5 rounded-md p-0 text-[11px]", className)}
    />
  );
}
