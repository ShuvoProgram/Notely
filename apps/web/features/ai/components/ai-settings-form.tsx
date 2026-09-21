"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { ArrowRight, Sparkles } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { aiApi } from "@/features/ai/api";
import { UserModelCard } from "@/features/ai/components/user-model-card";
import { messageFor } from "@/features/auth/components/auth-form-error";
import type { AIPreferences } from "@/lib/api/types";

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
  const models = [{ id: "__default", label: "Workspace default" }, ...data.models];
  const own = data.user_model?.enabled ? data.user_model : null;
  const ownLabel = own ? `${data.user_model_providers.find((p) => p.id === own.provider)?.label ?? own.provider} · ${own.model}` : null;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Assistant</CardTitle>
          <CardDescription>
            {ownLabel ? `Requests go to your own model (${ownLabel}).` : `Requests go through the Notely model gateway (${data.provider}).`} Your notes are never used to train models.
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
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="ai-model">Workspace model</Label>
                <Select value={current.model ?? "__default"} onValueChange={(v) => setPrefs({ ...current, model: v === "__default" ? null : v })} disabled={Boolean(own)}>
                  <SelectTrigger id="ai-model" className="w-full bg-background/60">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {models.map((m) => (
                      <SelectItem key={m.id} value={m.id}>
                        {m.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">{own ? "Not used while your own model is in use." : "Balanced for everyday work; Fast answers quicker on simple tasks."}</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="ai-summary">Summary length</Label>
                <Select value={current.summary_length} onValueChange={(v) => setPrefs({ ...current, summary_length: v as AIPreferences["summary_length"] })}>
                  <SelectTrigger id="ai-summary" className="w-full bg-background/60">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="short">Short — a few sentences</SelectItem>
                    <SelectItem value="medium">Medium — a short paragraph</SelectItem>
                    <SelectItem value="long">Long — a few paragraphs</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <label className="flex items-start gap-3 text-sm">
              <Checkbox checked={current.confirm_reads} onCheckedChange={(v) => setPrefs({ ...current, confirm_reads: v === true })} className="mt-0.5" aria-label="Ask before reading my notes too" />
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

      <UserModelCard key={data.user_model ? `${data.user_model.provider}:${data.user_model.model}:${data.user_model.enabled}:${data.user_model.key_hint}` : "none"} settings={data} />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="size-4 text-ai" aria-hidden /> What the assistant can do
          </CardTitle>
          <CardDescription>
            {data.tools.length} tools across your notes, tasks and connected apps. Reads run on their own; anything that changes data or sends something waits for your approval.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild variant="outline">
            <Link href="/app/settings/ai/tools">
              View all capabilities <ArrowRight aria-hidden />
            </Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
