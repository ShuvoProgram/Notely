"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { aiApi } from "@/features/ai/api";
import { messageFor } from "@/features/auth/components/auth-form-error";
import type { RiskLevel } from "@/lib/api/types";

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
          <ul className="divide-y">
            {audit.data.map((e) => (
              <li key={e.id} className="flex items-center gap-3 py-2 text-sm">
                {e.status === "completed" ? <Check className="size-4 shrink-0 text-success" aria-hidden /> : <XCircle className="size-4 shrink-0 text-destructive" aria-hidden />}
                <time className="w-24 shrink-0 text-xs text-muted-foreground" dateTime={e.created_at}>
                  {new Date(e.created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                </time>
                <span className="capitalize">{e.provider}</span>
                <span className="min-w-0 flex-1 truncate text-muted-foreground">{String(e.request_metadata["summary"] ?? e.tool_name ?? e.action)}</span>
                <Badge variant="outline" className="font-normal">
                  {RISK[e.risk_level]}
                </Badge>
                <span className="text-xs capitalize text-muted-foreground">{e.status}</span>
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
