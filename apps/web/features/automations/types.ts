/** Mirrors apps/api/app/automation/model.py (workflow v2) and app/schemas/automations.py. */

export type Operator =
  | "equals"
  | "not_equals"
  | "contains"
  | "not_contains"
  | "greater_than"
  | "less_than"
  | "exists"
  | "not_exists"
  | "is_empty"
  | "is_not_empty"
  | "is_true"
  | "is_false"
  | "before"
  | "after";

export interface ConditionRule {
  left: string;
  operator: Operator;
  right?: string | number | boolean | null;
}

export interface Condition {
  match: "all" | "any";
  rules: ConditionRule[];
  negate?: boolean;
}

interface StepBase {
  id: string;
  name?: string | null;
  enabled?: boolean;
}

export interface ActionStep extends StepBase {
  kind: "action";
  action: string;
  inputs: Record<string, unknown>;
  approval?: "ask" | "auto";
  on_error?: "stop" | "continue";
  retries?: number;
}

export interface FilterStep extends StepBase {
  kind: "filter";
  condition: Condition;
}

export interface BranchStep extends StepBase {
  kind: "branch";
  condition: Condition;
  then: Step[];
  otherwise: Step[];
}

export type Step = ActionStep | FilterStep | BranchStep;

export interface Workflow {
  version: 2;
  steps: Step[];
}

export type ScheduleKind = "once" | "daily" | "weekly" | "monthly" | "custom" | "interval" | "manual";

export interface Schedule {
  schedule_kind: ScheduleKind;
  schedule_config: { time?: string; days?: number[]; day?: number; every_minutes?: number; interval_days?: number };
  timezone: string;
  starts_at?: string | null;
  ends_at?: string | null;
}

export interface Issue {
  message: string;
  step_id?: string | null;
  field?: string | null;
  kind: "fix" | "connect" | "unsupported" | string;
  app?: string | null;
  fix_path?: string | null;
}

export type RunStatus = "queued" | "running" | "completed" | "stopped" | "failed" | "waiting_for_approval" | "skipped";

export interface LastRun {
  id: string;
  status: RunStatus;
  run_mode: string;
  summary: string | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface Automation extends Schedule {
  id: string;
  name: string;
  description: string | null;
  workflow: Workflow;
  next_run_at: string | null;
  enabled: boolean;
  status: string;
  consecutive_failures: number;
  created_at: string;
  updated_at: string;
  apps: string[];
  last_run: LastRun | null;
  running: boolean;
  pending_approvals: number;
  issues: Issue[];
}

export interface AutomationInput extends Schedule {
  name: string;
  description?: string | null;
  workflow: Workflow;
  enabled: boolean;
}

export interface Run {
  id: string;
  status: RunStatus;
  run_mode: "manual" | "scheduled" | "test" | string;
  summary: string | null;
  error: string | null;
  occurrence_at: string;
  started_at: string;
  finished_at: string | null;
  trigger: { type?: string; fired_at?: string; previous_run_at?: string | null };
}

export interface RunStep {
  step_id: string;
  position: number;
  kind: string;
  name: string | null;
  status: "pending" | "running" | "completed" | "simulated" | "skipped" | "failed" | "waiting_for_approval";
  summary: string | null;
  error: string | null;
  input: Record<string, unknown>;
  output: unknown;
  details: Record<string, unknown>;
  attempts: number;
  started_at: string | null;
  finished_at: string | null;
}

export interface Approval {
  id: string;
  execution_id: string;
  step_id: string;
  status: "pending" | "approved" | "rejected";
  proposal: { action?: string; app?: string; label?: string; summary?: string; safety?: string; inputs?: Record<string, string> };
  decided_at: string | null;
}

export interface RunDetail extends Run {
  steps: RunStep[];
  approvals: Approval[];
}

export interface InputSpec {
  key: string;
  label: string;
  type: "text" | "long_text" | "number" | "boolean" | "choice" | "list" | "date" | "datetime" | "note" | "email" | string;
  required: boolean;
  mappable: boolean;
  help?: string;
  options?: { value: string; label: string }[];
  default?: string | number | boolean;
  placeholder?: string;
}

export interface OutputSpec {
  key: string;
  label: string;
  type: "text" | "long_text" | "number" | "date" | "boolean" | "url" | "list" | "object" | string;
  fields?: OutputSpec[];
}

export type Safety = "safe" | "ask" | "always_ask";

export interface ActionSpec {
  id: string;
  app: string;
  app_name: string;
  app_logo: string | null;
  label: string;
  description: string;
  group: "find" | "do" | "ai";
  safety: Safety;
  safety_text: string;
  writes: boolean;
  available: boolean;
  inputs: InputSpec[];
  outputs: OutputSpec[];
}

export interface AppSpec {
  id: string;
  name: string;
  logo: string | null;
  category: string;
  connected: boolean;
  status: "connected" | "needs_attention" | "not_connected";
  connect_path: string | null;
}

export interface Catalog {
  apps: AppSpec[];
  actions: ActionSpec[];
}

export interface Template {
  id: string;
  name: string;
  description: string | null;
  builtin: boolean;
  apps: string[];
  workflow: Workflow;
  schedule_kind: ScheduleKind;
  schedule_config: Schedule["schedule_config"];
  available: boolean;
  missing_apps: string[];
  prompt: string | null;
}

export interface Draft {
  name: string | null;
  description: string | null;
  workflow: Workflow | null;
  schedule_kind: ScheduleKind | null;
  schedule_config: Schedule["schedule_config"];
  timezone: string | null;
  starts_at: string | null;
  questions: string[];
  missing_apps: { app: string; name: string; connect_path: string }[];
  unsupported: { request: string; reason: string; suggestion: string | null }[];
  changes: string[];
  issues: Issue[];
}
