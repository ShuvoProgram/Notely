import { api, apiEnvelope } from "@/lib/api/client";
import type { PlatformRole } from "@/lib/api/types";

/** Typed client for /api/v1/admin. The server authorizes every call; nothing here grants access. */

export type Permission = "admin:read" | "users:manage" | "roles:manage" | "platform:manage";

export interface AdminMe {
  id: string;
  email: string;
  display_name: string;
  role: PlatformRole;
  permissions: Permission[];
  admin_session_expires_at: string;
  two_factor_enabled: boolean;
}

export interface UserBrief {
  id: string;
  email: string;
  display_name: string;
}

export interface Window {
  days: number;
  since: string;
  until: string;
}

export interface PlatformEvent {
  id: string;
  category: "error" | "security" | "usage";
  kind: string;
  source: string | null;
  message: string | null;
  user: UserBrief | null;
  metadata: Record<string, unknown>;
  occurred_at: string;
}

export interface Overview {
  window: Window;
  users: {
    total: number;
    new: number;
    new_previous: number;
    active: { day: number; week: number; month: number; window: number };
    suspended: number;
    staff: number;
    growth: { date: string; signups: number; total: number }[];
    recent: (UserBrief & { created_at: string; is_active: boolean; role: PlatformRole })[];
  };
  usage: {
    notes_created: number;
    notes_total: number;
    tasks_created: number;
    tasks_completed: number;
    ai_conversations: number;
    ai_requests: number;
    automations_created: number;
    automations_total: number;
    automations_enabled: number;
    automation_runs: number;
    automation_runs_succeeded: number;
    automation_runs_failed: number;
    active_connections: number;
    connector_calls: number;
  };
  usage_series: { date: string; notes: number; ai_requests: number; automation_runs: number; tasks: number }[];
  health: {
    api_errors: number;
    job_failures: number;
    oauth_failures: number;
    connector_auth_failures: number;
    connections_needing_reauth: number;
    automation_runs_failed: number;
    ai_requests_failed: number;
    recent_incidents: PlatformEvent[];
    services: { database: boolean; redis: boolean };
  };
}

export interface AdminUserRow {
  id: string;
  email: string;
  display_name: string;
  role: PlatformRole;
  is_active: boolean;
  suspended_at: string | null;
  email_verified: boolean;
  two_factor_enabled: boolean;
  created_at: string;
  last_active_at: string | null;
  counts: { notes: number; automations: number; connections: number; ai_requests_30d: number };
}

export interface AuditRow {
  id: string;
  created_at: string;
  actor: { id: string | null; email: string | null; role: string | null };
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  resource_label: string | null;
  result: "success" | "denied" | "failed";
  ip: string | null;
  request_id: string | null;
  metadata: Record<string, unknown>;
}

export interface AdminUserDetail {
  profile: {
    id: string;
    email: string;
    display_name: string;
    role: PlatformRole;
    is_active: boolean;
    suspended_at: string | null;
    suspension_reason: string | null;
    email_verified: boolean;
    created_at: string;
    last_login_at: string | null;
    last_active_at: string | null;
    has_password: boolean;
    two_factor_enabled: boolean;
    sign_in_methods: string[];
    workspace: { name: string; kind: string } | null;
  };
  usage: { notes: number; notes_trashed: number; notes_created_30d: number; tasks_open: number; tasks_done: number };
  ai: {
    conversations: number;
    requests: number;
    requests_30d: number;
    failed: number;
    input_tokens: number;
    output_tokens: number;
    last_request_at: string | null;
    own_model: { provider: string; model: string; enabled: boolean } | null;
  };
  automations: {
    total: number;
    enabled: number;
    runs_30d: number;
    failed_30d: number;
    items: {
      id: string;
      name: string;
      enabled: boolean;
      schedule_kind: string;
      consecutive_failures: number;
      next_run_at: string | null;
      last_run_at: string | null;
      created_at: string;
    }[];
  };
  connections: {
    id: string;
    provider: string;
    name: string;
    status: string;
    auth_type: string;
    scopes_count: number;
    last_error_code: string | null;
    last_checked_at: string | null;
    last_sync_at: string | null;
    connected_at: string;
  }[];
  sessions: {
    id: string;
    device: string;
    ip: string | null;
    created_at: string;
    last_seen_at: string;
    expires_at: string;
    two_factor_verified: boolean;
  }[];
  activity: {
    id: string;
    provider: string;
    provider_name: string;
    action: string;
    tool: string | null;
    risk: string;
    status: string;
    created_at: string;
  }[];
  errors: { source: string; label?: string; message: string | null; code?: string | null; occurred_at: string; ref: string }[];
  security_events: PlatformEvent[];
  admin_actions: AuditRow[];
}

export interface DurationStats {
  count: number;
  avg_ms: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
  sampled: boolean;
}

export interface AutomationSummary {
  window: Window;
  automations: { total: number; enabled: number; paused_after_failures: number; event_triggered: number; created_in_window: number };
  executions: {
    total: number;
    succeeded: number;
    failed: number;
    waiting_for_approval: number;
    in_progress: number;
    success_rate: number | null;
    retried: number;
    by_status: Record<string, number>;
    by_mode: Record<string, number>;
    duration: DurationStats;
  };
  series: { date: string; succeeded: number; failed: number }[];
  top_failing: {
    id: string;
    name: string;
    owner: UserBrief | null;
    enabled: boolean;
    consecutive_failures: number;
    runs: number;
    failed: number;
    failure_rate: number | null;
    last_run_at: string | null;
  }[];
  failures_by_error: { error_type: string; count: number }[];
  failures_by_connector: { connector: string; name: string; count: number }[];
}

export interface ExecutionRow {
  id: string;
  automation: { id: string; name: string };
  owner: UserBrief | null;
  status: string;
  run_mode: string;
  attempts: number;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  error: string | null;
  error_type: string | null;
  connectors: string[];
  steps: number;
}

export interface ExecutionDetail {
  id: string;
  status: string;
  run_mode: string;
  attempts: number;
  occurrence_at: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  error: string | null;
  outcome: string | null;
  context_keys: string[];
  automation: {
    id: string;
    name: string;
    enabled: boolean;
    schedule_kind: string;
    timezone: string;
    consecutive_failures: number;
    next_run_at: string | null;
    created_at: string;
  };
  owner: UserBrief | null;
  steps: {
    step_id: string;
    position: number;
    kind: string;
    connector: string | null;
    name: string | null;
    status: string;
    attempts: number;
    error: string | null;
    error_type: string | null;
    input_fields: string[];
    has_output: boolean;
    started_at: string | null;
    finished_at: string | null;
    duration_ms: number | null;
  }[];
  approvals: { step_id: string; status: string; decided_at: string | null }[];
}

export type ConnectorHealth = "healthy" | "degraded" | "failing" | "unused" | "not_configured" | "disabled";

export interface ConnectorRow {
  provider: string;
  name: string;
  category: string;
  enabled: boolean;
  configured: boolean;
  health: ConnectorHealth;
  accounts: number;
  connected: number;
  expired: number;
  needs_attention: number;
  errored: number;
  disconnected: number;
  auth_failing: number;
  oauth_failures: number;
  auth_failures: number;
  calls: number;
  failed_calls: number;
  failure_rate: number | null;
  last_failure_at: string | null;
}

export interface ConnectorDetail {
  provider: string;
  name: string;
  connections_with_problems: {
    id: string;
    user: UserBrief | null;
    status: string;
    error_code: string | null;
    error: string | null;
    last_checked_at: string | null;
  }[];
  recent_failures: { id: string; user: UserBrief | null; action: string; tool: string | null; created_at: string }[];
  auth_events: PlatformEvent[];
}

export interface AIUsage {
  window: Window;
  requests: {
    total: number;
    failed: number;
    failure_rate: number | null;
    by_status: Record<string, number>;
    conversations: number;
    active_users: number;
  };
  tokens: { input: number; output: number; runs_without_usage: number };
  cost: { tracked: boolean; estimated_usd: number | null; runs_with_cost: number };
  latency: DurationStats;
  by_model: { provider: string; model: string; requests: number; failed: number; input_tokens: number; output_tokens: number }[];
  tools: {
    total: number;
    by_status: Record<string, number>;
    top: { tool: string; provider: string; provider_name: string; calls: number; failed: number }[];
  };
  automation_drafts: { succeeded: number; failed: number };
  own_model_users: number;
  top_users: { user: UserBrief | null; requests: number; input_tokens: number; output_tokens: number }[];
  series: { date: string; requests: number; failed: number; input_tokens: number; output_tokens: number }[];
}

export interface SettingItem {
  key: string;
  label: string;
  description: string;
  kind: "bool" | "int" | "text";
  group: "availability" | "features" | "limits";
  value: boolean | number | string | null;
  default: boolean | number | string | null;
  minimum: number | null;
  maximum: number | null;
  max_length: number | null;
  nullable: boolean;
  updated_at: string | null;
}

export interface AdminSettings {
  settings: SettingItem[];
  environment: {
    environment: string;
    ai: {
      provider: string;
      default_model: string;
      fast_model: string;
      gateway_key_configured: boolean;
      max_tool_iterations: number;
      request_timeout_seconds: number;
    };
    email: { configured: boolean; from_address: string | null };
    sign_in_providers: string[];
    connectors_configured: number;
    connectors_total: number;
    security: {
      admin_session_max_age_hours: number;
      admin_require_2fa: boolean;
      session_ttl_hours: number;
      rate_limit_auth_per_minute: number;
      rate_limit_ai_per_minute: number;
      encryption_configured: boolean;
    };
  };
  roles: Record<PlatformRole, Permission[]>;
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  extra: Record<string, unknown>;
}

type Params = Record<string, string | number | boolean | null | undefined>;

export function toQuery(params: Params): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

async function paged<T>(path: string, params: Params): Promise<Paged<T>> {
  const { data, meta } = await apiEnvelope<T[]>(`${path}${toQuery(params)}`);
  const { total, page, page_size, ...extra } = meta as { total: number; page: number; page_size: number };
  return { items: data, total, page, pageSize: page_size, extra };
}

const base = "/admin";

export const adminApi = {
  me: () => api.get<AdminMe>(`${base}/me`),
  overview: (days: number) => api.get<Overview>(`${base}/overview${toQuery({ days })}`),
  events: (params: Params) => paged<PlatformEvent>(`${base}/events`, params),
  users: (params: Params) => paged<AdminUserRow>(`${base}/users`, params),
  user: (id: string) => api.get<AdminUserDetail>(`${base}/users/${id}`),
  suspend: (id: string, reason: string, revokeSessions: boolean) =>
    api.post<{ id: string; is_active: boolean }>(`${base}/users/${id}/suspend`, { reason, revoke_sessions: revokeSessions }),
  reactivate: (id: string) => api.post<{ id: string; is_active: boolean }>(`${base}/users/${id}/reactivate`),
  revokeSessions: (id: string) => api.post<{ revoked: number }>(`${base}/users/${id}/sessions/revoke`),
  setRole: (id: string, role: PlatformRole) => api.patch<{ id: string; role: PlatformRole }>(`${base}/users/${id}/role`, { role }),
  automationSummary: (days: number) => api.get<AutomationSummary>(`${base}/automations/summary${toQuery({ days })}`),
  executions: (params: Params) => paged<ExecutionRow>(`${base}/automations/executions`, params),
  execution: (id: string) => api.get<ExecutionDetail>(`${base}/automations/executions/${id}`),
  connectors: (days: number) => api.get<ConnectorRow[]>(`${base}/connectors${toQuery({ days })}`),
  connector: (provider: string, days: number) => api.get<ConnectorDetail>(`${base}/connectors/${provider}${toQuery({ days })}`),
  setConnectorEnabled: (provider: string, enabled: boolean) =>
    api.patch<{ provider: string; enabled: boolean }>(`${base}/connectors/${provider}`, { enabled }),
  ai: (days: number) => api.get<AIUsage>(`${base}/ai${toQuery({ days })}`),
  audit: (params: Params) => paged<AuditRow>(`${base}/audit`, params),
  settings: () => api.get<AdminSettings>(`${base}/settings`),
  updateSettings: (changes: Record<string, unknown>) => api.patch<AdminSettings>(`${base}/settings`, { changes }),
};

export const adminKeys = {
  all: ["admin"] as const,
  me: ["admin", "me"] as const,
  overview: (days: number) => ["admin", "overview", days] as const,
  users: (params: Params) => ["admin", "users", params] as const,
  user: (id: string) => ["admin", "user", id] as const,
  automationSummary: (days: number) => ["admin", "automations", "summary", days] as const,
  executions: (params: Params) => ["admin", "automations", "executions", params] as const,
  execution: (id: string) => ["admin", "automations", "execution", id] as const,
  connectors: (days: number) => ["admin", "connectors", days] as const,
  connector: (provider: string, days: number) => ["admin", "connector", provider, days] as const,
  ai: (days: number) => ["admin", "ai", days] as const,
  audit: (params: Params) => ["admin", "audit", params] as const,
  events: (params: Params) => ["admin", "events", params] as const,
  settings: ["admin", "settings"] as const,
};
