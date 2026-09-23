"use client";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";

export function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

/** The user's picture, or their initials when there is none (or it fails to load). */
export function UserAvatar({ name, src, className, fallbackClassName }: { name: string; src?: string | null; className?: string; fallbackClassName?: string }) {
  return (
    <Avatar className={cn("size-8", className)}>
      {src ? <AvatarImage src={src} alt="" className="object-cover" /> : null}
      <AvatarFallback className={cn("bg-ai-soft text-xs font-bold text-foreground ring-1 ring-ai/40", fallbackClassName)}>{initialsOf(name) || "?"}</AvatarFallback>
    </Avatar>
  );
}
