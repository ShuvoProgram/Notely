import type {
  ActionSpec,
  ActionStep,
  BranchStep,
  Catalog,
  Condition,
  Operator,
  OutputSpec,
  RunStatus,
  Schedule,
  Step,
  TriggerSpec,
  Workflow,
} from "./types";

export const REF = /\{\{\s*([^{}]+?)\s*\}\}/g;
const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

// --- schedule ---------------------------------------------------------------------------------

export function formatClock(value: string | undefined): string {
  const [h, m] = (value || "09:00").split(":").map(Number);
  const date = new Date(2000, 0, 1, h ?? 9, m ?? 0);
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(date);
}

function ordinal(n: number): string {
  const suffix = n % 10 === 1 && n !== 11 ? "st" : n % 10 === 2 && n !== 12 ? "nd" : n % 10 === 3 && n !== 13 ? "rd" : "th";
  return `${n}${suffix}`;
}

/** The trigger an event automation is configured with (undefined when not in the catalog). */
export function findTrigger(config: Schedule["schedule_config"] | undefined, catalog: Catalog | undefined): TriggerSpec | undefined {
  if (!config?.provider || !config.trigger) return undefined;
  return catalog?.triggers?.find((t) => t.app === config.provider && t.name === config.trigger);
}

export function scheduleText(s: Pick<Schedule, "schedule_kind" | "schedule_config" | "starts_at">, catalog?: Catalog): string {
  const cfg = s.schedule_config ?? {};
  const at = formatClock(cfg.time);
  switch (s.schedule_kind) {
    case "event": {
      const trigger = findTrigger(cfg, catalog);
      if (trigger) return `When: ${trigger.label} · ${trigger.app_name}`;
      return cfg.trigger ? `When: ${humanKey(cfg.trigger)}` : "When something happens in an app";
    }
    case "manual":
      return "Only when you run it";
    case "interval": {
      const every = cfg.every_minutes ?? 60;
      return every % 60 === 0 ? `Every ${every === 60 ? "hour" : `${every / 60} hours`}` : `Every ${every} minutes`;
    }
    case "daily":
      return `Every day · ${at}`;
    case "weekly": {
      const days = [...(cfg.days ?? [])].sort();
      if (days.join() === "0,1,2,3,4") return `Every weekday · ${at}`;
      if (days.join() === "5,6") return `Every weekend · ${at}`;
      if (days.length === 7) return `Every day · ${at}`;
      return `Every ${days.map((d) => DAY_NAMES[d]?.slice(0, 3)).join(", ")} · ${at}`;
    }
    case "monthly":
      return `Monthly on the ${ordinal(cfg.day ?? 1)} · ${at}`;
    case "custom":
      return `Every ${cfg.interval_days ?? 1} days · ${at}`;
    case "once":
      return s.starts_at
        ? `Once · ${new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(s.starts_at))}`
        : "Once";
    default:
      return "On a schedule";
  }
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  const diff = date.getTime() - Date.now();
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (abs < 60_000) return diff < 0 ? "just now" : "in a moment";
  if (abs < 3_600_000) return rtf.format(Math.round(diff / 60_000), "minute");
  if (abs < 86_400_000) {
    const sameDay = new Date().toDateString() === date.toDateString();
    const time = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(date);
    if (sameDay) return `today at ${time}`;
    return rtf.format(Math.round(diff / 3_600_000), "hour");
  }
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

// --- steps ------------------------------------------------------------------------------------

export function* walk(steps: Step[], depth = 0): Generator<{ step: Step; depth: number }> {
  for (const step of steps) {
    yield { step, depth };
    if (step.kind === "branch") {
      yield* walk(step.then, depth + 1);
      yield* walk(step.otherwise, depth + 1);
    }
  }
}

export function allIds(workflow: Workflow): Set<string> {
  return new Set([...walk(workflow.steps)].map(({ step }) => step.id));
}

export function newId(base: string, taken: Set<string>): string {
  const clean = base.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40) || "step";
  const start = /^[a-z]/.test(clean) ? clean : `step_${clean}`;
  let id = start;
  for (let n = 2; taken.has(id); n++) id = `${start}_${n}`;
  return id;
}

export function findStep(steps: Step[], id: string): Step | undefined {
  for (const { step } of walk(steps)) if (step.id === id) return step;
  return undefined;
}

/** Replace, remove or insert steps anywhere in the tree (immutable). */
export function mapSteps(steps: Step[], fn: (step: Step, index: number, list: Step[]) => Step | Step[] | null): Step[] {
  const out: Step[] = [];
  steps.forEach((step, index) => {
    let current: Step = step;
    if (current.kind === "branch") {
      current = { ...current, then: mapSteps(current.then, fn), otherwise: mapSteps(current.otherwise, fn) };
    }
    const result = fn(current, index, steps);
    if (result === null) return;
    if (Array.isArray(result)) out.push(...result);
    else out.push(result);
  });
  return out;
}

export function actionOf(catalog: Catalog | undefined, step: Step): ActionSpec | undefined {
  return step.kind === "action" ? catalog?.actions.find((a) => a.id === step.action) : undefined;
}

export function appOf(catalog: Catalog | undefined, appId: string) {
  return catalog?.apps.find((a) => a.id === appId);
}

export function appName(catalog: Catalog | undefined, appId: string): string {
  return appOf(catalog, appId)?.name ?? appId.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Plain-language verb for the step's role in the flow. */
export function stepVerb(step: Step, action?: ActionSpec): string {
  if (step.kind === "filter") return "Check";
  if (step.kind === "branch") return "Decide";
  if (action?.group === "find") return "Find";
  if (action?.group === "ai") return "Think";
  return "Do";
}

/** The app a step belongs to ("gmail"), or its logic kind; tolerant of malformed data. */
export function appIdOf(step: Step): string {
  if (step.kind !== "action") return step.kind;
  return typeof step.action === "string" ? step.action.split(".")[0] || "unknown" : "unknown";
}

export function stepTitle(step: Step, catalog?: Catalog): string {
  if (step.name) return step.name;
  if (step.kind === "filter") return "Only continue if…";
  if (step.kind === "branch") return "Split into paths";
  const action = actionOf(catalog, step);
  if (action) return action.label;
  if (typeof step.action !== "string") return "Unknown step";
  return step.action.split(".").slice(1).join(" ").replaceAll("_", " ") || "Unknown step";
}

// --- conditions -------------------------------------------------------------------------------

export const OPERATORS: { value: Operator; label: string; unary?: boolean }[] = [
  { value: "is_not_empty", label: "has something", unary: true },
  { value: "is_empty", label: "is empty", unary: true },
  { value: "greater_than", label: "is more than" },
  { value: "less_than", label: "is less than" },
  { value: "equals", label: "is" },
  { value: "not_equals", label: "is not" },
  { value: "contains", label: "contains" },
  { value: "not_contains", label: "doesn't contain" },
  { value: "is_true", label: "is yes", unary: true },
  { value: "is_false", label: "is no", unary: true },
  { value: "before", label: "is before" },
  { value: "after", label: "is after" },
  { value: "exists", label: "exists", unary: true },
  { value: "not_exists", label: "doesn't exist", unary: true },
];

export const isUnary = (op: Operator) => OPERATORS.find((o) => o.value === op)?.unary ?? false;

export function emptyCondition(left = ""): Condition {
  return { match: "all", rules: [{ left, operator: "is_not_empty" }] };
}

// --- data mapping -----------------------------------------------------------------------------

export interface DataOption {
  path: string; // "steps.mail.output.results.count"
  label: string; // "Number of emails"
  type: string;
}

export interface DataSource {
  step: ActionStep;
  title: string;
  appId: string;
  options: DataOption[];
}

function singular(label: string): string {
  const lower = label.toLowerCase();
  if (lower.endsWith("ies")) return label.slice(0, -3) + "y";
  if (lower.endsWith("ses") || lower.endsWith("xes")) return label.slice(0, -2);
  if (lower.endsWith("s") && !lower.endsWith("ss")) return label.slice(0, -1);
  return label;
}

function fromOutputs(prefix: string, outputs: OutputSpec[]): DataOption[] {
  const out: DataOption[] = [];
  for (const field of outputs) {
    const path = `${prefix}.${field.key}`;
    if (field.type === "list") {
      out.push({ path, label: `All ${field.label.toLowerCase()}`, type: "list" });
      out.push({ path: `${path}.count`, label: `Number of ${field.label.toLowerCase()}`, type: "number" });
      for (const sub of field.fields ?? []) {
        out.push({ path: `${path}.0.${sub.key}`, label: `First ${singular(field.label).toLowerCase()} · ${sub.label}`, type: sub.type });
      }
    } else {
      out.push({ path, label: field.label, type: field.type });
    }
  }
  return out;
}

function humanKey(key: string): string {
  return key.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** When a connector doesn't describe its data, a test run's real output does. */
function fromSample(prefix: string, sample: unknown): DataOption[] {
  if (!sample || typeof sample !== "object" || Array.isArray(sample)) return [];
  const out: DataOption[] = [];
  for (const [key, value] of Object.entries(sample as Record<string, unknown>)) {
    if (["simulated", "message", "verified", "sources"].includes(key)) continue;
    const path = `${prefix}.${key}`;
    if (Array.isArray(value)) {
      out.push({ path, label: `All ${humanKey(key).toLowerCase()}`, type: "list" });
      out.push({ path: `${path}.count`, label: `Number of ${humanKey(key).toLowerCase()}`, type: "number" });
      const first = value[0];
      if (first && typeof first === "object" && !Array.isArray(first)) {
        for (const sub of Object.keys(first as Record<string, unknown>).slice(0, 12)) {
          out.push({ path: `${path}.0.${sub}`, label: `First ${singular(humanKey(key)).toLowerCase()} · ${humanKey(sub)}`, type: "text" });
        }
      }
    } else if (value === null || typeof value !== "object") {
      out.push({ path, label: humanKey(key), type: typeof value === "number" ? "number" : "text" });
    }
  }
  return out;
}

/** Steps whose data `targetId` may use: earlier steps on its path (mirrors the API rules). */
export function visibleSteps(steps: Step[], targetId: string): Step[] {
  let found: Step[] | null = null;
  const visit = (list: Step[], visible: Step[]): Step[] => {
    const produced: Step[] = [];
    for (const step of list) {
      if (found) return produced;
      if (step.id === targetId) {
        found = [...visible];
        return produced;
      }
      if (step.kind === "branch") {
        const a = visit(step.then, [...visible, step]);
        const b = found ? [] : visit(step.otherwise, [...visible, step]);
        visible = [...visible, ...a, ...b];
        produced.push(...a, ...b);
      }
      visible = [...visible, step];
      produced.push(step);
    }
    return produced;
  };
  visit(steps, []);
  return found ?? [];
}

export const EVERYTHING = "Everything from this step";

/** The data one action step offers: declared outputs, else what its last test returned. */
export function stepOptions(step: ActionStep, catalog: Catalog | undefined, samples: Record<string, unknown>): DataOption[] {
  const action = actionOf(catalog, step);
  const prefix = `steps.${step.id}.output`;
  const declared = action?.outputs.length ? fromOutputs(prefix, action.outputs) : [];
  const sampled = declared.length ? [] : fromSample(prefix, samples[step.id]);
  return [...declared, ...sampled, { path: prefix, label: EVERYTHING, type: "object" }];
}

export function dataSources(
  workflow: Workflow,
  targetId: string,
  catalog: Catalog | undefined,
  samples: Record<string, unknown>,
): DataSource[] {
  return visibleSteps(workflow.steps, targetId)
    .filter((s): s is ActionStep => s.kind === "action")
    .map((step) => ({
      step,
      title: stepTitle(step, catalog),
      appId: appIdOf(step),
      options: stepOptions(step, catalog, samples),
    }));
}

export const TRIGGER_OPTIONS: DataOption[] = [
  { path: "trigger.fired_at", label: "When this run started", type: "date" },
  { path: "trigger.previous_run_at", label: "When it last ran", type: "date" },
  { path: "automation.name", label: "Automation name", type: "text" },
];

/** What `{{trigger.*}}` offers: the schedule basics, or the fields of the event that started the run. */
export function triggerOptions(schedule: Pick<Schedule, "schedule_kind" | "schedule_config"> | undefined, catalog: Catalog | undefined): DataOption[] {
  const trigger = schedule?.schedule_kind === "event" ? findTrigger(schedule.schedule_config, catalog) : undefined;
  if (!trigger) return TRIGGER_OPTIONS;
  return [
    ...trigger.outputs.map((o) => ({ path: `trigger.${o.key}`, label: o.label, type: o.type })),
    { path: "automation.name", label: "Automation name", type: "text" },
  ];
}

/** "Gmail · Emails › First email · Subject" for a `steps.x.output…` reference. */
export function referenceLabel(
  path: string,
  workflow: Workflow,
  catalog: Catalog | undefined,
  samples: Record<string, unknown> = {},
  triggers: DataOption[] = TRIGGER_OPTIONS,
): string {
  const trigger = triggers.find((o) => o.path === path) ?? TRIGGER_OPTIONS.find((o) => o.path === path);
  if (trigger) return trigger.label;
  // An event trigger field whose trigger is not in view (e.g. a card without the catalog).
  if (path.startsWith("trigger.")) return `Trigger › ${humanKey(path.slice("trigger.".length))}`;
  const match = /^steps\.([a-z][a-z0-9_]*)\.output(?:\.(.*))?$/.exec(path);
  if (!match) return path;
  const step = findStep(workflow.steps, match[1]!);
  if (!step) return "Missing step";
  const option = step.kind === "action" ? stepOptions(step, catalog, samples).find((o) => o.path === path) : undefined;
  const title = stepTitle(step, catalog);
  if (option) return option.label === EVERYTHING ? title : `${title} › ${option.label}`;
  return `${title} › ${(match[2] ?? "").split(".").filter((p) => !/^\d+$/.test(p)).map(humanKey).join(" › ")}`;
}

export type Token = { text: string } | { ref: string };

export function tokenize(value: string): Token[] {
  const tokens: Token[] = [];
  let last = 0;
  for (const match of value.matchAll(REF)) {
    if (match.index! > last) tokens.push({ text: value.slice(last, match.index) });
    tokens.push({ ref: match[1]!.trim() });
    last = match.index! + match[0].length;
  }
  if (last < value.length) tokens.push({ text: value.slice(last) });
  return tokens;
}

/** Every step id a reference string points at (to keep data links valid on reorder/delete). */
export function referencedSteps(value: unknown): string[] {
  const text = JSON.stringify(value ?? "");
  return [...text.matchAll(/steps\.([a-z][a-z0-9_]*)\.output/g)].map((m) => m[1]!);
}

// --- runs -------------------------------------------------------------------------------------

export const RUN_STATUS: Record<RunStatus, { label: string; tone: string }> = {
  queued: { label: "Starting", tone: "text-muted-foreground" },
  running: { label: "Running", tone: "text-info" },
  completed: { label: "Finished", tone: "text-success" },
  stopped: { label: "Finished early", tone: "text-success" },
  failed: { label: "Needs attention", tone: "text-destructive" },
  waiting_for_approval: { label: "Waiting for you", tone: "text-warning" },
  skipped: { label: "Skipped", tone: "text-muted-foreground" },
};

export function emptyWorkflow(): Workflow {
  return { version: 2, steps: [] };
}

export function isBranch(step: Step): step is BranchStep {
  return step.kind === "branch";
}

// --- editing the tree -------------------------------------------------------------------------

export interface ListLocation {
  parent: string | null;
  arm: "then" | "otherwise" | null;
}

/** Apply `fn` to the list at `location` (the main flow or one path of a branch). */
export function editList(steps: Step[], location: ListLocation, fn: (list: Step[]) => Step[]): Step[] {
  if (location.parent === null) return fn(steps);
  return mapSteps(steps, (step) =>
    step.kind === "branch" && step.id === location.parent && location.arm
      ? { ...step, [location.arm]: fn(step[location.arm]) }
      : step,
  );
}

export function locate(steps: Step[], id: string, location: ListLocation = { parent: null, arm: null }): (ListLocation & { index: number }) | null {
  const index = steps.findIndex((s) => s.id === id);
  if (index >= 0) return { ...location, index };
  for (const step of steps) {
    if (step.kind !== "branch") continue;
    for (const arm of ["then", "otherwise"] as const) {
      const found = locate(step[arm], id, { parent: step.id, arm });
      if (found) return found;
    }
  }
  return null;
}

export function removeStep(steps: Step[], id: string): Step[] {
  return mapSteps(steps, (step) => (step.id === id ? null : step));
}

export function moveStep(steps: Step[], id: string, direction: -1 | 1): Step[] {
  const where = locate(steps, id);
  if (!where) return steps;
  return editList(steps, where, (list) => {
    const target = where.index + direction;
    if (target < 0 || target >= list.length) return list;
    const next = [...list];
    [next[where.index], next[target]] = [next[target]!, next[where.index]!];
    return next;
  });
}

export function cloneWithNewIds(step: Step, taken: Set<string>): Step {
  const id = newId(`${step.id}_copy`, taken);
  taken.add(id);
  if (step.kind !== "branch") return { ...structuredClone(step), id };
  return {
    ...structuredClone(step),
    id,
    then: step.then.map((s) => cloneWithNewIds(s, taken)),
    otherwise: step.otherwise.map((s) => cloneWithNewIds(s, taken)),
  };
}

export function stepRefs(step: Step): string[] {
  return referencedSteps(step.kind === "action" ? step.inputs : step.condition);
}

/** First step that uses data from a step it can't see (after a move), if any. */
export function brokenReference(workflow: Workflow): { step: Step; missing: string } | null {
  for (const { step } of walk(workflow.steps)) {
    const visible = new Set(visibleSteps(workflow.steps, step.id).map((s) => s.id));
    const missing = stepRefs(step).find((ref) => !visible.has(ref) && ref !== step.id);
    if (missing) return { step, missing };
  }
  return null;
}

export function usersOf(workflow: Workflow, id: string): Step[] {
  return [...walk(workflow.steps)].map(({ step }) => step).filter((s) => s.id !== id && stepRefs(s).includes(id));
}
