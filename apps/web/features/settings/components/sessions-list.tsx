"use client";

import { Laptop, Smartphone } from "@/components/icons";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { useLogoutOthers, useRevokeSession, useSessions } from "@/features/auth/hooks";
import type { UserSession } from "@/lib/api/types";

export function describeAgent(ua: string | null): { label: string; mobile: boolean } {
  if (!ua) return { label: "Unknown device", mobile: false };
  const mobile = /Mobile|Android|iPhone|iPad/i.test(ua);
  const browser =
    /Edg\//.test(ua) ? "Edge"
    : /OPR\//.test(ua) ? "Opera"
    : /Chrome\//.test(ua) ? "Chrome"
    : /Firefox\//.test(ua) ? "Firefox"
    : /Safari\//.test(ua) ? "Safari"
    : "Browser";
  const os =
    /Windows/.test(ua) ? "Windows"
    : /Mac OS X/.test(ua) ? "macOS"
    : /Android/.test(ua) ? "Android"
    : /iPhone|iPad/.test(ua) ? "iOS"
    : /Linux/.test(ua) ? "Linux"
    : "";
  return { label: os ? `${browser} on ${os}` : browser, mobile };
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

function SessionRow({ session }: { session: UserSession }) {
  const revoke = useRevokeSession();
  const { label, mobile } = describeAgent(session.user_agent);
  const Icon = mobile ? Smartphone : Laptop;
  return (
    <li className="flex items-center gap-3 py-3">
      <Icon className="size-5 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">
          {label}
          {session.current ? (
            <span className="ml-2 rounded-full bg-ai-soft px-2 py-0.5 text-[11px] font-medium text-ai">
              This device
            </span>
          ) : null}
        </p>
        <p className="truncate text-xs text-muted-foreground">
          {session.ip_address ?? "IP unknown"} · Active {relativeTime(session.last_seen_at)}
        </p>
      </div>
      {!session.current ? (
        <Button
          variant="ghost"
          size="sm"
          disabled={revoke.isPending}
          onClick={() =>
            revoke.mutate(session.id, {
              onSuccess: () => toast.success("Session signed out"),
              onError: (error) => toast.error(messageFor(error)),
            })
          }
        >
          Sign out
        </Button>
      ) : null}
    </li>
  );
}

export function SessionsList() {
  const { data: sessions, isPending, error } = useSessions();
  const logoutOthers = useLogoutOthers();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Active sessions</CardTitle>
        <CardDescription>Devices currently signed in to your account.</CardDescription>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <div className="space-y-3">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : error ? (
          <p role="alert" className="text-sm text-destructive">
            {messageFor(error)}
          </p>
        ) : (
          <>
            <ul className="divide-y">
              {sessions?.map((s) => <SessionRow key={s.id} session={s} />)}
            </ul>
            {sessions && sessions.length > 1 ? (
              <Button
                variant="outline"
                className="mt-4"
                disabled={logoutOthers.isPending}
                onClick={() =>
                  logoutOthers.mutate(undefined, {
                    onSuccess: (r) => toast.success(`Signed out ${r.revoked} other ${r.revoked === 1 ? "device" : "devices"}`),
                    onError: (e) => toast.error(messageFor(e)),
                  })
                }
              >
                Sign out all other devices
              </Button>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
