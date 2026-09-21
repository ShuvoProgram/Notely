"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, ExternalLink, KeyRound, Loader2, Pencil, RefreshCw, ShieldCheck, Trash2, XCircle } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { aiApi } from "@/features/ai/api";
import { ModelPicker, formatContext } from "@/features/ai/components/model-picker";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { ApiError } from "@/lib/api/client";
import type { AISettings, ModelInfo, ModelTestResult, UserModelProvider } from "@/lib/api/types";
import { playSfx } from "@/lib/sfx/player";

function isValidBaseUrl(value: string): boolean {
  try {
    const u = new URL(value.trim());
    return (u.protocol === "http:" || u.protocol === "https:") && !u.username && !u.password;
  } catch {
    return false;
  }
}

/**
 * Bring your own model. Two modes:
 * - locked: the saved configuration as a read-only summary (provider, model, endpoint, key
 *   hint, verification). Nothing here can be changed by accident; "Edit configuration" and
 *   "Replace API key" are explicit.
 * - editing: provider + searchable model picker (live list from the vendor once a key is
 *   present) + endpoint + write-only key. "Test" tries the draft without saving; "Save" is
 *   verify-then-write on the server, so a working configuration is only replaced by another
 *   working one, and the card locks again.
 */
export function UserModelCard({ settings }: { settings: AISettings }) {
  const saved = settings.user_model;
  const [editing, setEditing] = React.useState(!saved);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="size-4" aria-hidden /> Your own model
        </CardTitle>
        <CardDescription>Use your own OpenAI, Anthropic, Google or OpenRouter key — or any OpenAI-compatible server such as Ollama — instead of the workspace gateway. Keys are encrypted at rest, used only for your requests, and never shown again.</CardDescription>
      </CardHeader>
      <CardContent>
        {!settings.encryption_available ? (
          <p role="alert" className="mb-4 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm">
            This deployment has no encryption key configured, so API keys can&apos;t be stored safely. Ask your administrator to set <code>ENCRYPTION_KEY</code>.
          </p>
        ) : null}
        {saved && !editing ? <SavedConfiguration settings={settings} onEdit={() => setEditing(true)} /> : <ConfigurationForm key={saved ? `${saved.provider}:${saved.model}` : "new"} settings={settings} onDone={() => setEditing(false)} onCancel={saved ? () => setEditing(false) : undefined} />}
      </CardContent>
    </Card>
  );
}

function SavedConfiguration({ settings, onEdit }: { settings: AISettings; onEdit: () => void }) {
  const queryClient = useQueryClient();
  const saved = settings.user_model!;
  const provider = settings.user_model_providers.find((p) => p.id === saved.provider);
  const known = provider?.models.find((m) => m.id === saved.model);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["ai", "settings"] });
  const [confirmRemove, setConfirmRemove] = React.useState(false);
  const [testResult, setTestResult] = React.useState<ModelTestResult | null>(null);
  const test = useMutation({
    mutationFn: () => aiApi.testUserModel(),
    onSuccess: (r) => {
      playSfx(r.ok ? "success" : "error");
      setTestResult(r);
      invalidate();
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => aiApi.setUserModel({ provider: saved.provider, model: saved.model, base_url: saved.base_url, enabled, verify: false }),
    onSuccess: (row) => {
      invalidate();
      toast.success(row.enabled ? "Your model is in use" : "Back to the workspace gateway");
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  const remove = useMutation({
    mutationFn: aiApi.deleteUserModel,
    onSuccess: () => {
      playSfx("delete");
      setConfirmRemove(false);
      invalidate();
      toast.success("Configuration removed", { description: "Requests go through the workspace gateway again." });
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  return (
    <div className="space-y-4">
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
        <dt className="text-muted-foreground">Provider</dt>
        <dd>{provider?.label ?? saved.provider}</dd>
        <dt className="text-muted-foreground">Model</dt>
        <dd className="min-w-0">
          <span className="font-medium">{known?.name ?? saved.model}</span>
          {known && known.name !== saved.model ? <span className="ml-2 font-mono text-xs text-muted-foreground">{saved.model}</span> : null}
          {known?.context ? <span className="ml-2 text-xs text-muted-foreground">{formatContext(known.context)}</span> : null}
        </dd>
        {saved.base_url && !provider?.base_url_fixed ? (
          <>
            <dt className="text-muted-foreground">Endpoint</dt>
            <dd className="truncate font-mono text-xs">{saved.base_url}</dd>
          </>
        ) : null}
        <dt className="text-muted-foreground">API key</dt>
        <dd className="font-mono tracking-widest">{saved.key_hint ? `••••••••••••${saved.key_hint.replace("…", "")}` : provider?.key_optional ? "none (local server)" : "••••••••"}</dd>
        <dt className="text-muted-foreground">Status</dt>
        <dd className="flex flex-wrap items-center gap-2">
          {saved.verified_at ? (
            <Badge variant="outline" className="gap-1 font-normal text-success">
              <ShieldCheck className="size-3" aria-hidden /> Configuration verified
            </Badge>
          ) : saved.last_error ? (
            <Badge variant="outline" className="gap-1 font-normal text-destructive" title={saved.last_error}>
              <XCircle className="size-3" aria-hidden /> Last test failed
            </Badge>
          ) : (
            <Badge variant="secondary" className="font-normal">
              Not tested yet
            </Badge>
          )}
          {saved.supports_tools === false ? (
            <Badge variant="outline" className="gap-1 font-normal text-warning">
              <AlertTriangle className="size-3" aria-hidden /> Chat only — no tool calls
            </Badge>
          ) : null}
          <Badge variant={saved.enabled ? "default" : "secondary"} className="font-normal">
            {saved.enabled ? "In use" : "Saved, not in use"}
          </Badge>
        </dd>
      </dl>
      {saved.last_error && !saved.verified_at ? <p className="text-xs text-destructive">{saved.last_error}</p> : null}
      {testResult ? (
        <p role="status" className={testResult.ok ? "text-sm text-success" : "text-sm text-destructive"}>
          {testResult.ok ? "Works: " : "Failed: "}
          {testResult.detail}
        </p>
      ) : null}
      <label className="flex items-start gap-3 text-sm">
        <Checkbox checked={saved.enabled} disabled={toggle.isPending} onCheckedChange={(v) => toggle.mutate(v === true)} className="mt-0.5" aria-label="Use this model for my assistant" />
        <span>
          Use this model for my assistant
          <span className="block text-xs text-muted-foreground">Untick to keep the configuration but go back to the workspace gateway.</span>
        </span>
      </label>
      <div className="flex flex-wrap gap-2">
        <Button type="button" onClick={onEdit}>
          <Pencil aria-hidden /> Edit configuration
        </Button>
        <Button type="button" variant="outline" disabled={test.isPending} onClick={() => test.mutate()}>
          {test.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <RefreshCw aria-hidden />} Test again
        </Button>
        <Button type="button" variant="ghost" className="text-muted-foreground hover:text-destructive" onClick={() => setConfirmRemove(true)}>
          <Trash2 aria-hidden /> Remove
        </Button>
      </div>
      <ConfirmDialog
        open={confirmRemove}
        onOpenChange={setConfirmRemove}
        title="Remove your model configuration?"
        description="The stored API key is deleted from Notely and your assistant goes back to the workspace gateway. You can set it up again any time."
        confirmLabel="Remove"
        pending={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </div>
  );
}

function ConfigurationForm({ settings, onDone, onCancel }: { settings: AISettings; onDone: () => void; onCancel?: () => void }) {
  const queryClient = useQueryClient();
  const providers = settings.user_model_providers;
  const saved = settings.user_model;
  const [providerId, setProviderId] = React.useState(saved?.provider ?? providers[0]?.id ?? "openai");
  const info: UserModelProvider | undefined = providers.find((p) => p.id === providerId);
  const [model, setModel] = React.useState(saved?.model ?? "");
  const [baseUrl, setBaseUrl] = React.useState(saved?.base_url ?? info?.default_base_url ?? "");
  const [apiKey, setApiKey] = React.useState("");
  const [replacingKey, setReplacingKey] = React.useState(!saved?.key_hint);
  const [enabled, setEnabled] = React.useState(saved?.enabled ?? true);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [testResult, setTestResult] = React.useState<ModelTestResult | null>(null);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["ai", "settings"] });

  const sameProviderAsSaved = saved?.provider === providerId && !!saved?.key_hint;
  const hasKey = apiKey.trim() !== "" || (sameProviderAsSaved && !replacingKey) || info?.key_optional || info?.id === "openrouter";
  const effectiveBase = info?.base_url_fixed ? (info.default_base_url ?? "") : info?.needs_base_url ? baseUrl : "";
  const baseOk = !info?.needs_base_url || info.base_url_fixed || isValidBaseUrl(baseUrl);
  const draft = { provider: providerId, model: model.trim(), base_url: info?.needs_base_url && !info.base_url_fixed ? baseUrl.trim() || null : null, api_key: apiKey || null };

  // Live model list from the vendor, keyed by the inputs that produced it so stale answers are ignored.
  const signature = `${providerId}|${apiKey}|${effectiveBase}`;
  const [live, setLive] = React.useState<{ signature: string; models?: ModelInfo[]; error?: string } | null>(null);
  const listModels = useMutation({
    mutationFn: async () => ({ signature, ...(await aiApi.listUserModels({ provider: providerId, api_key: apiKey || null, base_url: draft.base_url })) }),
    onSuccess: (r) => setLive({ signature: r.signature, models: r.models }),
    onError: (e) => setLive({ signature, error: messageFor(e) }),
  });
  const refreshModels = listModels.mutate;
  React.useEffect(() => {
    if (!hasKey || !baseOk || !info?.live_models) return;
    const handle = window.setTimeout(() => refreshModels(), apiKey ? 700 : 0);
    return () => window.clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refetch when the inputs that matter change
  }, [signature, hasKey, baseOk]);
  const liveModels = live?.signature === signature && live.models ? live.models : null;
  const liveError = live?.signature === signature ? (live.error ?? null) : null;
  const options = liveModels ?? info?.models ?? [];
  const unknownModel = liveModels !== null && liveModels.length > 0 && model !== "" && !liveModels.some((m) => m.id === model);

  const test = useMutation({
    mutationFn: () => aiApi.testUserModel(draft),
    onSuccess: (r) => {
      playSfx(r.ok ? "success" : "error");
      setTestResult(r);
    },
    onError: (e) => {
      if (e instanceof ApiError && Object.keys(e.fieldErrors).length) setErrors(Object.fromEntries(Object.entries(e.fieldErrors).map(([k, v]) => [k, v[0] ?? "Invalid"])));
      else toast.error(messageFor(e));
    },
  });
  const save = useMutation({
    mutationFn: () => aiApi.setUserModel({ ...draft, enabled, verify: true }),
    onSuccess: (row) => {
      playSfx("success");
      setApiKey("");
      setErrors({});
      invalidate();
      toast.success("Configuration saved and verified", { description: row.supports_tools === false ? "This endpoint cannot call tools, so the assistant can chat but not search or act." : `${row.model} answered.` });
      onDone();
    },
    onError: (error) => {
      playSfx("error");
      if (error instanceof ApiError && error.code === "MODEL_TEST_FAILED") {
        setTestResult({ ok: false, detail: error.message, latency_ms: null, supports_tools: null });
        return;
      }
      if (error instanceof ApiError && Object.keys(error.fieldErrors).length) {
        setErrors(Object.fromEntries(Object.entries(error.fieldErrors).map(([k, v]) => [k, v[0] ?? "Invalid"])));
        return;
      }
      toast.error(messageFor(error));
    },
  });

  const pickProvider = (id: string) => {
    const next = providers.find((p) => p.id === id);
    setProviderId(id);
    setModel(saved?.provider === id ? saved.model : (next?.models[0]?.id ?? ""));
    setBaseUrl(saved?.provider === id && saved.base_url ? saved.base_url : (next?.default_base_url ?? ""));
    setReplacingKey(!(saved?.provider === id && saved.key_hint));
    setApiKey("");
    setErrors({});
    setTestResult(null);
  };
  const ready = model.trim() !== "" && baseOk && (hasKey || Boolean(info?.key_optional));

  return (
    <form
      className="space-y-5"
      autoComplete="off"
      onSubmit={(e) => {
        e.preventDefault();
        if (ready) save.mutate();
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="byo-provider">Provider</Label>
          <Select value={providerId} onValueChange={pickProvider}>
            <SelectTrigger id="byo-provider" className="w-full bg-background/60">
              <SelectValue placeholder="Choose a provider" />
            </SelectTrigger>
            <SelectContent>
              {providers.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            {info?.tagline}
            {info?.docs_url ? (
              <>
                {" · "}
                <a href={info.docs_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline-offset-2 hover:underline">
                  Get an API key <ExternalLink className="size-3" aria-hidden />
                </a>
              </>
            ) : null}
          </p>
        </div>
        <div className="space-y-2">
          <Label htmlFor="byo-model">Model</Label>
          <ModelPicker id="byo-model" value={model} onChange={setModel} options={options} loading={listModels.isPending} invalid={Boolean(errors.model) || unknownModel} groupByPrice={providerId === "openrouter"} />
          {errors.model ? (
            <p role="alert" className="text-xs text-destructive">
              {errors.model}
            </p>
          ) : liveError ? (
            <p role="alert" className="text-xs text-destructive">
              Couldn&apos;t list models: {liveError}
            </p>
          ) : liveModels ? (
            <p className="text-xs text-muted-foreground" aria-live="polite">
              {unknownModel ? <span className="text-warning">“{model}” isn&apos;t among the {liveModels.length} models available to this key.</span> : `${liveModels.length} models available${providerId === "openrouter" ? ", free ones first" : " to your key"}.`}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">{info?.live_models ? (hasKey ? "Loading the models your key can use…" : "Suggested models — enter your API key to load the ones it can use.") : "Type the model name your server serves."}</p>
          )}
        </div>
      </div>

      {info?.needs_base_url && !info.base_url_fixed ? (
        <div className="space-y-2">
          <Label htmlFor="byo-base">Base URL</Label>
          <Input id="byo-base" type="url" inputMode="url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder={info.default_base_url ?? "https://…/v1"} aria-invalid={errors.base_url || (baseUrl !== "" && !baseOk) ? true : undefined} className="bg-background/60 font-mono text-sm" />
          {errors.base_url || (baseUrl !== "" && !baseOk) ? (
            <p role="alert" className="text-xs text-destructive">
              {errors.base_url ?? "Enter a full http(s) URL ending in /v1, e.g. http://localhost:11434/v1"}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">The server&apos;s OpenAI-compatible root — Ollama, LM Studio, vLLM, Groq, Together, Azure-compatible gateways.</p>
          )}
        </div>
      ) : null}

      <div className="space-y-2">
        <Label htmlFor="byo-key">API key</Label>
        {sameProviderAsSaved && !replacingKey ? (
          <div className="flex items-center justify-between gap-3 rounded-md border border-glass-border bg-background/60 px-3 py-2 text-sm">
            <span className="font-mono tracking-widest">••••••••••••{saved?.key_hint.replace("…", "")}</span>
            <Button type="button" variant="outline" size="sm" onClick={() => setReplacingKey(true)}>
              Replace API key
            </Button>
          </div>
        ) : (
          <>
            <Input id="byo-key" name="byo-api-key" type="password" autoComplete="new-password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={info?.key_placeholder} aria-invalid={errors.api_key ? true : undefined} className="bg-background/60" />
            {sameProviderAsSaved ? (
              <Button type="button" variant="link" size="sm" className="h-auto px-0 text-xs" onClick={() => { setReplacingKey(false); setApiKey(""); }}>
                Keep the stored key
              </Button>
            ) : null}
          </>
        )}
        {errors.api_key ? (
          <p role="alert" className="text-xs text-destructive">
            {errors.api_key}
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">Sent once over HTTPS, encrypted at rest, never displayed again.{info?.key_optional ? " Optional for local servers." : ""}</p>
        )}
      </div>

      <label className="flex items-start gap-3 text-sm">
        <Checkbox checked={enabled} onCheckedChange={(v) => setEnabled(v === true)} className="mt-0.5" aria-label="Use this model for my assistant" />
        <span>
          Use this model for my assistant
          <span className="block text-xs text-muted-foreground">Untick to save the configuration but keep using the workspace gateway.</span>
        </span>
      </label>

      {testResult ? (
        <p role="status" className={testResult.ok ? "flex items-start gap-2 text-sm text-success" : "flex items-start gap-2 text-sm text-destructive"}>
          {testResult.ok ? <Check className="mt-0.5 size-4 shrink-0" aria-hidden /> : <XCircle className="mt-0.5 size-4 shrink-0" aria-hidden />}
          <span>{testResult.detail}</span>
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" disabled={!ready || test.isPending || save.isPending} onClick={() => test.mutate()}>
          {test.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <Check aria-hidden />} Test
        </Button>
        <Button type="submit" disabled={!ready || save.isPending || test.isPending || !settings.encryption_available}>
          {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null} {save.isPending ? "Verifying & saving…" : "Save configuration"}
        </Button>
        {onCancel ? (
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        ) : null}
      </div>
      <p className="text-xs text-muted-foreground">Saving runs a test first; your current configuration is only replaced once the new one answers.</p>
    </form>
  );
}
