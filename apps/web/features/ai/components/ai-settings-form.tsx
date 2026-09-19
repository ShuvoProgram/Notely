"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { aiApi } from "@/features/ai/api";
import { messageFor } from "@/features/auth/components/auth-form-error";
import type { AIPreferences, RiskLevel } from "@/lib/api/types";

const RISK_LABEL: Record<RiskLevel, string> = {
  read: "Reads · runs automatically",
  write: "Changes · needs your approval",
  external_communication: "Sends externally · needs approval",
  destructive: "Destructive · needs approval",
};

export function AISettingsForm() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["ai", "settings"], queryFn: aiApi.settings });
  const [prefs, setPrefs] = React.useState<AIPreferences | null>(null);
  const current = prefs ?? settings.data?.preferences ?? null;

  const save = useMutation({
    mutationFn: aiApi.updateSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ai", "settings"] });
      setPrefs(null);
      toast.success("AI preferences saved");
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  if (settings.isPending || !current) return <Skeleton className="h-64 w-full rounded-xl" />;
  if (settings.error) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {messageFor(settings.error)}
      </p>
    );
  }
  const data = settings.data;
  const models = [{ id: "", label: "Workspace default" }, ...data.models];

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Assistant</CardTitle>
          <CardDescription>
            Requests go through the Notely model gateway ({data.provider}); your notes are never used to train models.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-5"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate({ ...current, model: current.model || null });
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="ai-model">Model</Label>
              <select
                id="ai-model"
                value={current.model ?? ""}
                onChange={(e) => setPrefs({ ...current, model: e.target.value || null })}
                className="h-9 w-full rounded-md border bg-transparent px-3 text-sm"
              >
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ai-summary">Summary length</Label>
              <select
                id="ai-summary"
                value={current.summary_length}
                onChange={(e) => setPrefs({ ...current, summary_length: e.target.value as AIPreferences["summary_length"] })}
                className="h-9 w-full rounded-md border bg-transparent px-3 text-sm"
              >
                <option value="short">Short — a few sentences</option>
                <option value="medium">Medium — a short paragraph</option>
                <option value="long">Long — a few paragraphs</option>
              </select>
            </div>
            <label className="flex items-start gap-3 text-sm">
              <input
                type="checkbox"
                className="mt-0.5 size-4 accent-[var(--ai)]"
                checked={current.confirm_reads}
                onChange={(e) => setPrefs({ ...current, confirm_reads: e.target.checked })}
              />
              <span>
                Ask before reading my notes too
                <span className="block text-xs text-muted-foreground">Changes always require approval; this extends that to searches and reads.</span>
              </span>
            </label>
            <Button type="submit" disabled={save.isPending || prefs === null}>
              {save.isPending ? "Saving…" : "Save preferences"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>What the assistant can do</CardTitle>
          <CardDescription>Every tool has a risk level. Nothing marked as a change runs without your review.</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="divide-y">
            {data.tools.map((t) => (
              <li key={t.name} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{t.name}</code>
                <span className="flex-1 text-muted-foreground">{t.description}</span>
                <Badge variant={t.risk === "read" ? "outline" : "secondary"} className="font-normal">
                  {RISK_LABEL[t.risk]}
                </Badge>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
