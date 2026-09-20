"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, ExternalLink, KeyRound, Loader2, ShieldCheck, Trash2, XCircle } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { aiApi } from "@/features/ai/api";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { ApiError } from "@/lib/api/client";
import type { AISettings, ModelTestResult, UserModelProvider } from "@/lib/api/types";

/**
 * Bring your own model: provider + model + API key stored encrypted on the server. The key is
 * write-only — the form never receives it back, only a hint — and "Test" runs a real, tiny
 * completion so a wrong key or model name is caught before it breaks the assistant.
 */
export function UserModelCard({ settings }: { settings: AISettings }) {
  const queryClient = useQueryClient();
  const providers = settings.user_model_providers;
  const saved = settings.user_model;
  const [providerId, setProviderId] = React.useState(saved?.provider ?? providers[0]?.id ?? "openai");
  const info: UserModelProvider | undefined = providers.find((p) => p.id === providerId);
  const [model, setModel] = React.useState(saved?.model ?? "");
  const [baseUrl, setBaseUrl] = React.useState(saved?.base_url ?? "");
  const [apiKey, setApiKey] = React.useState("");
  const [enabled, setEnabled] = React.useState(saved?.enabled ?? true);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [testResult, setTestResult] = React.useState<ModelTestResult | null>(null);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["ai", "settings"] });

  const save = useMutation({
    mutationFn: () =>
      aiApi.setUserModel({
        provider: providerId,
        model,
        base_url: info?.needs_base_url ? baseUrl : null,
        api_key: apiKey || null,
        enabled,
      }),
    onSuccess: () => {
      setApiKey("");
      setErrors({});
      setTestResult(null);
      invalidate();
      toast.success("Model saved");
    },
    onError: (error) => {
      if (error instanceof ApiError && Object.keys(error.fieldErrors).length) {
        setErrors(Object.fromEntries(Object.entries(error.fieldErrors).map(([k, v]) => [k, v[0] ?? "Invalid"])));
        return;
      }
      toast.error(messageFor(error));
    },
  });
  const test = useMutation({
    mutationFn: aiApi.testUserModel,
    onSuccess: (r) => {
      setTestResult(r);
      invalidate();
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  const remove = useMutation({
    mutationFn: aiApi.deleteUserModel,
    onSuccess: () => {
      setModel("");
      setBaseUrl("");
      setApiKey("");
      setTestResult(null);
      invalidate();
      toast.success("Back to the workspace gateway");
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  const pickProvider = (id: string) => {
    setProviderId(id);
    const next = providers.find((p) => p.id === id);
    setModel(next?.models[0] ?? "");
    setBaseUrl(next?.default_base_url ?? "");
    setErrors({});
  };
  const dirty = saved ? saved.provider !== providerId || saved.model !== model || (saved.base_url ?? "") !== (info?.needs_base_url ? baseUrl : "") || saved.enabled !== enabled || apiKey !== "" : true;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="size-4" aria-hidden /> Your own model
        </CardTitle>
        <CardDescription>
          Use your own OpenAI, Anthropic or Google key — or any OpenAI-compatible server such as Ollama — instead of the workspace gateway. Your key is stored encrypted, never shown again, and only used for your requests.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {!settings.encryption_available ? (
          <p role="alert" className="mb-4 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm">
            This deployment has no encryption key configured, so API keys can&apos;t be stored safely. Ask your administrator to set <code>ENCRYPTION_KEY</code>.
          </p>
        ) : null}
        {saved ? (
          <div className="mb-4 flex flex-wrap items-center gap-2 text-sm" aria-live="polite">
            <Badge variant={saved.enabled ? "default" : "secondary"} className="font-normal">
              {saved.enabled ? "In use" : "Saved, not in use"}
            </Badge>
            <span className="text-muted-foreground">
              {providers.find((p) => p.id === saved.provider)?.label ?? saved.provider} · {saved.model} · key {saved.key_hint || "set"}
            </span>
            {saved.verified_at ? (
              <Badge variant="outline" className="gap-1 font-normal">
                <ShieldCheck className="size-3" aria-hidden /> Verified
              </Badge>
            ) : saved.last_error ? (
              <Badge variant="destructive" className="gap-1 font-normal" title={saved.last_error}>
                <XCircle className="size-3" aria-hidden /> Last test failed
              </Badge>
            ) : (
              <Badge variant="secondary" className="font-normal">
                Not tested yet
              </Badge>
            )}
          </div>
        ) : null}
        <form
          className="space-y-4"
          autoComplete="off"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="byo-provider">Provider</Label>
              {/* A themed menu rather than a native <select>: Chromium paints native option
                  lists with the OS palette, which is unreadable on the dark theme. */}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button id="byo-provider" type="button" variant="outline" className="w-full justify-between font-normal">
                    {info?.label ?? "Choose a provider"}
                    <ChevronDown className="size-4 opacity-60" aria-hidden />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-(--radix-dropdown-menu-trigger-width)">
                  <DropdownMenuRadioGroup value={providerId} onValueChange={pickProvider}>
                    {providers.map((p) => (
                      <DropdownMenuRadioItem key={p.id} value={p.id}>
                        {p.label}
                      </DropdownMenuRadioItem>
                    ))}
                  </DropdownMenuRadioGroup>
                </DropdownMenuContent>
              </DropdownMenu>
              {info?.docs_url ? (
                <a href={info.docs_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-2 hover:underline">
                  Get an API key <ExternalLink className="size-3" aria-hidden />
                </a>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="byo-model">Model</Label>
              <Input id="byo-model" name="byo-model-name" autoComplete="off" list="byo-models" value={model} onChange={(e) => setModel(e.target.value)} placeholder={info?.models[0] ?? "model name"} aria-invalid={errors.model ? true : undefined} />
              <datalist id="byo-models">{info?.models.map((m) => <option key={m} value={m} />)}</datalist>
              {errors.model ? (
                <p role="alert" className="text-xs text-destructive">
                  {errors.model}
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">Pick a suggestion or type any model your key can use.</p>
              )}
            </div>
          </div>
          {info?.needs_base_url ? (
            <div className="space-y-2">
              <Label htmlFor="byo-base">Base URL</Label>
              <Input id="byo-base" type="url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder={info.default_base_url ?? "https://…/v1"} aria-invalid={errors.base_url ? true : undefined} />
              {errors.base_url ? (
                <p role="alert" className="text-xs text-destructive">
                  {errors.base_url}
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">The OpenAI-compatible endpoint, e.g. Ollama, LM Studio, OpenRouter or Groq.</p>
              )}
            </div>
          ) : null}
          <div className="space-y-2">
            <Label htmlFor="byo-key">API key</Label>
            <Input id="byo-key" name="byo-api-key" type="password" autoComplete="new-password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={saved?.key_hint ? `Stored (${saved.key_hint}) — enter a new key to replace it` : info?.key_placeholder} aria-invalid={errors.api_key ? true : undefined} />
            {errors.api_key ? (
              <p role="alert" className="text-xs text-destructive">
                {errors.api_key}
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">Sent once over HTTPS and encrypted at rest. Notely never displays it again.</p>
            )}
          </div>
          <label className="flex items-start gap-3 text-sm">
            <input type="checkbox" className="mt-0.5 size-4 accent-[var(--ai)]" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            <span>
              Use this model for my assistant
              <span className="block text-xs text-muted-foreground">Untick to keep the key but go back to the workspace gateway.</span>
            </span>
          </label>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={save.isPending || !settings.encryption_available || !model.trim() || !dirty}>
              {save.isPending ? "Saving…" : "Save model"}
            </Button>
            <Button type="button" variant="outline" disabled={!saved || test.isPending || dirty} onClick={() => test.mutate()}>
              {test.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />} Test
            </Button>
            {saved ? (
              <Button type="button" variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate()}>
                <Trash2 aria-hidden /> Remove key
              </Button>
            ) : null}
          </div>
          {testResult ? (
            <p role="status" className={testResult.ok ? "text-sm text-success" : "text-sm text-destructive"}>
              {testResult.ok ? "Works: " : "Failed: "}
              {testResult.detail}
            </p>
          ) : null}
        </form>
      </CardContent>
    </Card>
  );
}
