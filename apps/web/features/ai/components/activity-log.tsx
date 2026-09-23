"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, ShieldQuestion, XCircle } from "@/components/icons";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { aiApi } from "@/features/ai/api";
import { messageFor } from "@/features/auth/components/auth-form-error";
import type { RiskLevel } from "@/lib/api/types";
import { providerLabel } from "@/lib/providers";

const RISK: Record<RiskLevel, string> = { read: "Read", write: "Change", external_communication: "External", destructive: "Destructive" };

/** Audit log of every tool execution — metadata only, never note content. */
export function ActivityLog() {
  const audit = useQuery({ queryKey: ["audit"], queryFn: aiApi.audit });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Activity</CardTitle>
        <CardDescription>Everything the assistant did on your behalf, most recent first.</CardDescription>
      </CardHeader>
      <CardContent>
        {audit.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : audit.error ? (
          <p role="alert" className="text-sm text-destructive">
            {messageFor(audit.error)}
          </p>
        ) : audit.data?.length ? (
          <ul className="divide-y divide-glass-border">
            {audit.data.map((e) => (
              <li key={e.id} className="grid grid-cols-[auto_minmax(0,1fr)] items-start gap-x-3 gap-y-1 py-2.5 text-sm sm:flex sm:items-center">
                {e.status === "completed" || e.status === "verified" ? (
                  <Check className="mt-0.5 size-4 shrink-0 text-success sm:mt-0" aria-hidden />
                ) : e.status === "unverified" ? (
                  <ShieldQuestion className="mt-0.5 size-4 shrink-0 text-warning sm:mt-0" aria-hidden />
                ) : (
                  <XCircle className="mt-0.5 size-4 shrink-0 text-destructive sm:mt-0" aria-hidden />
                )}
                <div className="min-w-0 sm:contents">
                  <span className="mr-2 font-medium sm:mr-0">{providerLabel(e.provider)}</span>
                  <span className="block min-w-0 text-muted-foreground sm:inline sm:flex-1 sm:truncate">
                    {e.action === "verify" ? `Checked: ${e.tool_name ?? ""}` : String(e.request_metadata["summary"] ?? e.tool_name ?? e.action)}
                  </span>
                  <span className="mt-1 flex flex-wrap items-center gap-2 sm:contents">
                    <time className="text-xs text-muted-foreground sm:order-first sm:w-24 sm:shrink-0" dateTime={e.created_at}>
                      {new Date(e.created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                    </time>
                    <Badge variant="outline" className="font-normal">
                      {RISK[e.risk_level]}
                    </Badge>
                    <span className="text-xs capitalize text-muted-foreground">{e.status}</span>
                  </span>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No activity yet.</p>
        )}
      </CardContent>
    </Card>
  );
}
