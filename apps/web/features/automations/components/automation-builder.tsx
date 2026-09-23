"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  BookmarkPlus,
  Copy,
  FlaskConical,
  Loader2,
  MoreHorizontal,
  Play,
  Save,
  Trash2,
} from "@/components/icons";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { notesApi } from "@/features/notes/api";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { automationsApi } from "../api";
import {
  EVERYTHING,
  allIds,
  brokenReference,
  cloneWithNewIds,
  dataSources,
  editList,
  emptyWorkflow,
  findStep,
  locate,
  mapSteps,
  moveStep,
  newId,
  referenceLabel,
  removeStep,
  scheduleText,
  stepTitle,
  usersOf,
  type DataSource,
} from "../lib";
import type { ActionSpec, ActionStep, Automation, AutomationInput, Catalog, Condition, Draft, Issue, RunDetail, RunStep, Step, Template } from "../types";
import { ActionPicker } from "./action-picker";
import { AIAssist } from "./ai-assist";
import { RunHistory } from "./run-panel";
import { ScheduleEditor } from "./schedule-editor";
import { StepList, type BuilderContext, type InsertKind, type Slot } from "./step-list";

export const DRAFT_KEY = ["automation-draft"] as const;

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = React.useState(value);
  React.useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

const browserZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

function blank(): AutomationInput {
  return {
    name: "",
    description: null,
    workflow: emptyWorkflow(),
    schedule_kind: "weekly",
    schedule_config: { time: "09:00", days: [0, 1, 2, 3, 4] },
    timezone: browserZone(),
    starts_at: null,
    ends_at: null,
    enabled: false,
  };
}

function fromAutomation(a: Automation): AutomationInput {
  return {
    name: a.name,
    description: a.description,
    workflow: a.workflow,
    schedule_kind: a.schedule_kind,
    schedule_config: a.schedule_config,
    timezone: a.timezone,
    starts_at: a.starts_at,
    ends_at: a.ends_at,
    enabled: a.enabled,
  };
}

export function fromDraft(draft: Draft, base: AutomationInput = blank()): AutomationInput {
  return {
    ...base,
    name: draft.name || base.name,
    description: draft.description ?? base.description,
    workflow: draft.workflow ?? base.workflow,
    schedule_kind: draft.schedule_kind ?? base.schedule_kind,
    schedule_config: draft.schedule_kind ? draft.schedule_config : base.schedule_config,
    timezone: draft.timezone || base.timezone,
    starts_at: draft.starts_at ?? base.starts_at,
  };
}

function fromTemplate(t: Template): AutomationInput {
  return { ...blank(), name: t.name, description: t.description, workflow: structuredClone(t.workflow), schedule_kind: t.schedule_kind, schedule_config: t.schedule_config };
}

/** Pre-fill a new step's data fields from the nearest earlier step, the way a person would. */
function prefill(action: ActionSpec, sources: DataSource[]): Record<string, unknown> {
  const inputs: Record<string, unknown> = {};
  const nearest = [...sources].reverse();
  for (const field of action.inputs) {
    if (field.default !== undefined) inputs[field.key] = field.default;
    if (!field.mappable || !field.required) continue;
    if (field.type === "list") {
      const list = nearest.flatMap((s) => s.options).find((o) => o.type === "list");
      if (list) inputs[field.key] = `{{${list.path}}}`;
    } else if (field.key === "data") {
      const source = nearest[0];
      const list = source?.options.find((o) => o.type === "list");
      if (source) inputs[field.key] = `{{${(list ?? source.options.find((o) => o.label === EVERYTHING))!.path}}}`;
    } else if (["content", "message", "body"].includes(field.key)) {
      const ai = nearest.find((s) => s.appId === "ai");
      const text = ai?.options.find((o) => o.type === "long_text");
      if (text) inputs[field.key] = `{{${text.path}}}`;
    }
  }
  return inputs;
}

function defaultCondition(sources: DataSource[]): Condition {
  const options = [...sources].reverse().flatMap((s) => s.options);
  const count = options.find((o) => o.path.endsWith(".count"));
  if (count) return { match: "all", rules: [{ left: `{{${count.path}}}`, operator: "greater_than", right: 0 }] };
  const first = options[0];
  return { match: "all", rules: [{ left: first ? `{{${first.path}}}` : "", operator: "is_not_empty" }] };
}

function outputsOf(run: RunDetail): Record<string, unknown> {
  return Object.fromEntries(run.steps.filter((s) => s.output != null && (s.status === "completed" || s.status === "simulated")).map((s) => [s.step_id, s.output]));
}

type PickerTarget = { mode: "insert"; slot: Slot } | { mode: "replace"; id: string };

function Builder({
  initial,
  initialId,
  catalog,
  initialRun,
  initialSamples,
}: {
  initial: AutomationInput;
  initialId: string | null;
  catalog: Catalog;
  initialRun: string | null;
  initialSamples: Record<string, unknown>;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [form, setForm] = React.useState(initial);
  const [savedId, setSavedId] = React.useState(initialId);
  const [dirty, setDirty] = React.useState(!initialId);
  const [openId, setOpenId] = React.useState<string | null>(null);
  const [picker, setPicker] = React.useState<PickerTarget | null>(null);
  const [samples, setSamples] = React.useState(initialSamples);
  const [testSteps, setTestSteps] = React.useState<Record<string, RunStep>>({});
  const [activeRun, setActiveRun] = React.useState<string | null>(initialRun);
  const [panel, setPanel] = React.useState<"steps" | "runs">(initialRun ? "runs" : "steps");
  const [serverIssues, setServerIssues] = React.useState<Issue[] | null>(null);
  const [pendingDelete, setPendingDelete] = React.useState<{ id: string; users: string[] } | null>(null);
  const [confirmRemoveAutomation, setConfirmRemoveAutomation] = React.useState(false);

  const notes = useQuery({ queryKey: ["automation-note-targets"], queryFn: () => notesApi.list({ view: "active", limit: 100 }) });
  const workflowKey = useDebounced(JSON.stringify(form.workflow), 600);
  const validation = useQuery({
    queryKey: ["automation-validate", workflowKey],
    queryFn: () => automationsApi.validate(JSON.parse(workflowKey)),
    enabled: form.workflow.steps.length > 0,
    staleTime: 60_000,
  });
  const issues = React.useMemo<Issue[]>(() => serverIssues ?? validation.data?.issues ?? [], [serverIssues, validation.data]);

  React.useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const change = (patch: Partial<AutomationInput>) => {
    setForm((f) => ({ ...f, ...patch }));
    setDirty(true);
    setServerIssues(null);
  };
  const setSteps = (fn: (steps: Step[]) => Step[]) => {
    setForm((f) => ({ ...f, workflow: { ...f.workflow, steps: fn(f.workflow.steps) } }));
    setDirty(true);
    setServerIssues(null);
  };

  const labelsVersion = `${catalog.actions.length}:${Object.keys(samples).join(",")}`;
  const labelFor = React.useCallback((path: string) => referenceLabel(path, form.workflow, catalog, samples), [form.workflow, catalog, samples]);

  const showError = (error: unknown) => {
    if (error instanceof ApiError && Array.isArray(error.details.issues)) {
      setServerIssues(error.details.issues as Issue[]);
      const first = (error.details.issues as Issue[])[0];
      if (first?.step_id) setOpenId(first.step_id);
    }
    toast.error(messageFor(error));
  };

  const persist = async (patch: Partial<AutomationInput> = {}): Promise<Automation> => {
    const input = { ...form, ...patch, name: (patch.name ?? form.name).trim() || "Untitled automation" };
    const saved = savedId ? await automationsApi.update(savedId, input) : await automationsApi.create(input);
    if (!savedId) window.history.replaceState(null, "", `/app/automations/${saved.id}`);
    setSavedId(saved.id);
    setForm((f) => ({ ...f, name: input.name, enabled: saved.enabled }));
    setDirty(false);
    setServerIssues(saved.issues.length ? saved.issues : null);
    void queryClient.invalidateQueries({ queryKey: ["automations"] });
    return saved;
  };

  const save = useMutation({
    mutationFn: () => persist(),
    onSuccess: (saved) => toast.success(saved.issues.length ? "Saved as a draft — a few details still need filling in." : "Saved"),
    onError: showError,
  });
  const toggle = useMutation({
    mutationFn: async (enabled: boolean) => (dirty || !savedId ? persist({ enabled }) : automationsApi.setEnabled(savedId, enabled)),
    onSuccess: (saved) => {
      setForm((f) => ({ ...f, enabled: saved.enabled }));
      void queryClient.invalidateQueries({ queryKey: ["automations"] });
      toast.success(saved.enabled ? `On — ${scheduleText(saved).toLowerCase()}` : "Turned off");
    },
    onError: showError,
  });
  const test = useMutation({
    mutationFn: async (stepId?: string) => {
      const id = dirty || !savedId ? (await persist()).id : savedId;
      return automationsApi.test(id, stepId);
    },
    onSuccess: (run) => {
      setActiveRun(run.id);
      setPanel("runs");
    },
    onError: showError,
  });
  const runNow = useMutation({
    mutationFn: async () => {
      const id = dirty || !savedId ? (await persist()).id : savedId;
      return automationsApi.run(id);
    },
    onSuccess: (run) => {
      setActiveRun(run.id);
      setPanel("runs");
    },
    onError: showError,
  });
  const duplicate = useMutation({
    mutationFn: () => automationsApi.duplicate(savedId!),
    onSuccess: (copy) => router.push(`/app/automations/${copy.id}`),
    onError: showError,
  });
  const saveTemplate = useMutation({
    mutationFn: async () => automationsApi.saveTemplate(dirty ? (await persist()).id : savedId!),
    onSuccess: () => {
      toast.success("Saved as a template");
      void queryClient.invalidateQueries({ queryKey: ["automation-templates"] });
    },
    onError: showError,
  });
  const remove = useMutation({
    mutationFn: () => automationsApi.remove(savedId!),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["automations"] });
      router.push("/app/automations");
    },
    onError: showError,
  });

  const onRunFinished = React.useCallback((run: RunDetail) => {
    setSamples((s) => ({ ...s, ...outputsOf(run) }));
    if (run.run_mode === "test") setTestSteps(Object.fromEntries(run.steps.map((s) => [s.step_id, s])));
  }, []);

  const insertStep = (slot: Slot, step: Step) => {
    setSteps((steps) => editList(steps, slot, (list) => [...list.slice(0, slot.index), step, ...list.slice(slot.index)]));
    setOpenId(step.id);
  };

  const sourcesAt = (slot: Slot): DataSource[] => {
    const probe: Step = { kind: "filter", id: "__new__", condition: { match: "all", rules: [] } };
    const probeFlow = { ...form.workflow, steps: editList(form.workflow.steps, slot, (list) => [...list.slice(0, slot.index), probe, ...list.slice(slot.index)]) };
    return dataSources(probeFlow, "__new__", catalog, samples);
  };

  const ctx: BuilderContext = {
    workflow: form.workflow,
    catalog,
    samples,
    notes: notes.data?.notes ?? [],
    issues,
    testSteps,
    labelFor,
    labelsVersion,
    openId,
    setOpenId,
    testing: test.isPending,
    update: (step) => setSteps((steps) => mapSteps(steps, (s) => (s.id === step.id ? step : s))),
    remove: (id) => {
      const users = usersOf(form.workflow, id).map((s) => stepTitle(s, catalog));
      if (users.length) setPendingDelete({ id, users });
      else setSteps((steps) => removeStep(steps, id));
    },
    move: (id, direction) => {
      const next = { ...form.workflow, steps: moveStep(form.workflow.steps, id, direction) };
      const broken = brokenReference(next);
      if (broken && !brokenReference(form.workflow)) {
        toast.error(`“${stepTitle(broken.step, catalog)}” uses data from a step that would then come after it.`);
        return;
      }
      setSteps(() => next.steps);
    },
    duplicate: (id) => {
      const where = locate(form.workflow.steps, id);
      const step = findStep(form.workflow.steps, id);
      if (!where || !step) return;
      const copy = cloneWithNewIds(step, allIds(form.workflow));
      insertStep({ parent: where.parent, arm: where.arm, index: where.index + 1 }, copy);
    },
    insert: (slot: Slot, kind: InsertKind) => {
      if (kind === "action") return setPicker({ mode: "insert", slot });
      const sources = sourcesAt(slot);
      const id = newId(kind === "filter" ? "check" : "paths", allIds(form.workflow));
      insertStep(
        slot,
        kind === "filter"
          ? { kind: "filter", id, condition: defaultCondition(sources) }
          : { kind: "branch", id, condition: defaultCondition(sources), then: [], otherwise: [] },
      );
    },
    changeAction: (id) => setPicker({ mode: "replace", id }),
    testThrough: (id) => test.mutate(id),
  };

  const pickAction = (action: ActionSpec) => {
    if (!picker) return;
    if (picker.mode === "insert") {
      const sources = sourcesAt(picker.slot);
      const step: ActionStep = { kind: "action", id: newId(action.id.split(".")[1] ?? action.label, allIds(form.workflow)), action: action.id, inputs: prefill(action, sources) };
      insertStep(picker.slot, step);
    } else {
      const current = findStep(form.workflow.steps, picker.id);
      if (current?.kind !== "action") return;
      const where = locate(form.workflow.steps, picker.id);
      const probeSlot = where ? { parent: where.parent, arm: where.arm, index: where.index } : { parent: null, arm: null, index: 0 };
      ctx.update({ ...current, action: action.id, inputs: prefill(action, sourcesAt(probeSlot)), name: null });
    }
  };

  const applyDraft = (draft: Draft) => {
    setForm((f) => fromDraft(draft, f));
    setDirty(true);
    setServerIssues(null);
    toast.success("Changes applied — review them, then save.");
  };

  const busy = save.isPending || toggle.isPending || test.isPending || runNow.isPending;
  const stepCount = form.workflow.steps.length;

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0 flex-1 space-y-1">
          <Link href="/app/automations" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="size-4" aria-hidden /> Automations
          </Link>
          <input
            aria-label="Automation name"
            value={form.name}
            onChange={(e) => change({ name: e.target.value })}
            placeholder="Name this automation"
            className="block w-full truncate rounded-md bg-transparent text-2xl font-semibold tracking-tight outline-none placeholder:text-tertiary focus-visible:ring-2 focus-visible:ring-ring/40"
          />
          <p className="text-sm text-muted-foreground">{scheduleText(form)}{form.enabled ? " · On" : " · Off"}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="mr-1 flex items-center gap-2 text-sm">
            <Switch checked={form.enabled} disabled={busy || !stepCount} onCheckedChange={(on) => toggle.mutate(on)} aria-label="Automation on" />
            {form.enabled ? "On" : "Off"}
          </label>
          <Button variant="outline" disabled={busy || !stepCount} onClick={() => test.mutate(undefined)}>
            {test.isPending ? <Loader2 className="animate-spin" /> : <FlaskConical />} Test
          </Button>
          <Button variant="outline" disabled={busy || !stepCount} onClick={() => runNow.mutate()}>
            {runNow.isPending ? <Loader2 className="animate-spin" /> : <Play />} Run now
          </Button>
          <Button disabled={busy || !stepCount || (!dirty && !!savedId)} onClick={() => save.mutate()}>
            {save.isPending ? <Loader2 className="animate-spin" /> : <Save />} {dirty || !savedId ? "Save" : "Saved"}
          </Button>
          {savedId ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" aria-label="More">
                  <MoreHorizontal className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => duplicate.mutate()}>
                  <Copy /> Duplicate
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => saveTemplate.mutate()}>
                  <BookmarkPlus /> Save as template
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onSelect={() => setTimeout(() => setConfirmRemoveAutomation(true), 0)}>
                  <Trash2 /> Delete automation
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
      </div>

      <div className="flex gap-1 rounded-full bg-muted/40 p-1 lg:hidden" role="tablist" aria-label="Builder sections">
        {(["steps", "runs"] as const).map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={panel === tab}
            onClick={() => setPanel(tab)}
            className={cn("flex-1 rounded-full py-1.5 text-sm", panel === tab ? "bg-background font-medium shadow-1" : "text-muted-foreground")}
          >
            {tab === "steps" ? "Steps" : "Test & runs"}
          </button>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className={cn("min-w-0 space-y-4", panel !== "steps" && "hidden lg:block")}>
          <section className="glass rounded-2xl p-4" aria-labelledby="when-title">
            <h2 id="when-title" className="mb-3 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">When this happens</h2>
            <ScheduleEditor value={form} onChange={(schedule) => change(schedule)} />
          </section>

          {issues.length ? (
            <section className="rounded-2xl border border-warning/30 bg-warning/5 p-4" aria-label="Things to finish">
              <p className="flex items-center gap-2 text-sm font-medium text-warning">
                <AlertTriangle className="size-4" aria-hidden />
                {issues.length === 1 ? "One thing to finish before this can run" : `${issues.length} things to finish before this can run`}
              </p>
              <ul className="mt-2 space-y-1 text-sm">
                {issues.map((issue, i) => (
                  <li key={i} className="flex flex-wrap items-center gap-x-2">
                    <span>{issue.message}</span>
                    {issue.step_id ? (
                      <button type="button" className="text-ai underline underline-offset-2" onClick={() => setOpenId(issue.step_id!)}>
                        Show
                      </button>
                    ) : null}
                    {issue.kind === "connect" && issue.fix_path ? (
                      <Link href={issue.fix_path} className="text-ai underline underline-offset-2">
                        Connect
                      </Link>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section aria-label="Steps">
            <h2 className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Then do this</h2>
            <StepList steps={form.workflow.steps} ctx={ctx} />
          </section>
        </div>

        <aside className={cn("min-w-0 space-y-4 lg:sticky lg:top-4 lg:self-start", panel !== "runs" && "hidden lg:block")}>
          {stepCount ? <AIAssist form={form} onApply={applyDraft} /> : null}
          <section aria-labelledby="runs-title" className="space-y-3">
            <h2 id="runs-title" className="text-sm font-semibold">Test & run history</h2>
            {savedId ? (
              <RunHistory automationId={savedId} selected={activeRun} onSelect={setActiveRun} onFinished={onRunFinished} />
            ) : (
              <p className="rounded-2xl border border-dashed border-glass-border p-4 text-sm text-muted-foreground">
                Press <strong>Test</strong> to try it safely: Notely reads your data and runs AI for real, but only pretends to make changes.
              </p>
            )}
          </section>
        </aside>
      </div>

      <ActionPicker open={picker !== null} onOpenChange={(o) => !o && setPicker(null)} catalog={catalog} onPick={pickAction} />
      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title="Delete this step?"
        description={`${pendingDelete?.users.join(", ")} ${pendingDelete && pendingDelete.users.length > 1 ? "use" : "uses"} its data and will need new data chosen.`}
        confirmLabel="Delete step"
        onConfirm={() => {
          if (pendingDelete) setSteps((steps) => removeStep(steps, pendingDelete.id));
          setPendingDelete(null);
        }}
      />
      <ConfirmDialog
        open={confirmRemoveAutomation}
        onOpenChange={setConfirmRemoveAutomation}
        title="Delete this automation?"
        description="It stops running and its history is deleted. This can't be undone."
        confirmLabel="Delete"
        pending={remove.isPending}
        onConfirm={() => remove.mutate()}
      />
    </div>
  );
}

/** Loads what the builder needs, then mounts it seeded (new, from a template, an AI draft or saved). */
export function AutomationEditor({ automationId, templateId, fromAIDraft, runId }: { automationId?: string; templateId?: string; fromAIDraft?: boolean; runId?: string }) {
  const queryClient = useQueryClient();
  const catalog = useQuery({ queryKey: ["automation-catalog"], queryFn: automationsApi.catalog });
  const automation = useQuery({ queryKey: ["automations", automationId], queryFn: () => automationsApi.get(automationId!), enabled: !!automationId });
  const templates = useQuery({ queryKey: ["automation-templates"], queryFn: automationsApi.templates, enabled: !!templateId });
  const latestRun = useQuery({
    queryKey: ["automations", automationId, "latest-run-samples"],
    queryFn: async () => {
      const runs = await automationsApi.runs(automationId!);
      const recent = runs.find((r) => ["completed", "stopped", "waiting_for_approval"].includes(r.status)) ?? runs[0];
      return recent ? outputsOf(await automationsApi.runDetail(automationId!, recent.id)) : {};
    },
    enabled: !!automationId,
  });
  const [draft] = React.useState(() => (fromAIDraft ? queryClient.getQueryData<Draft>(DRAFT_KEY) : undefined));

  const error = catalog.error ?? automation.error;
  if (error) return <p role="alert" className="text-sm text-destructive">{messageFor(error)}</p>;
  const ready = catalog.data && (!automationId || (automation.data && latestRun.isFetched)) && (!templateId || templates.data);
  if (!ready) {
    return (
      <div className="space-y-4" aria-busy>
        <Skeleton className="h-16 rounded-2xl" />
        <Skeleton className="h-32 rounded-2xl" />
        <Skeleton className="h-48 rounded-2xl" />
      </div>
    );
  }
  const template = templates.data?.find((t) => t.id === templateId);
  const initial = automation.data ? fromAutomation(automation.data) : draft ? fromDraft(draft) : template ? fromTemplate(template) : blank();
  return (
    <Builder
      key={automationId ?? templateId ?? "new"}
      initial={initial}
      initialId={automation.data?.id ?? null}
      catalog={catalog.data!}
      initialRun={runId ?? null}
      initialSamples={latestRun.data ?? {}}
    />
  );
}
