/** Mirrors `apps/api/app/schemas/auth.py`. Keep in sync until shared-types is generated from OpenAPI. */

export interface User {
  id: string;
  tenant_id: string;
  email: string;
  email_verified: boolean;
  display_name: string;
  avatar_url: string | null;
  has_password: boolean;
  created_at: string;
  /** In-app notification switches by kind group; a missing key means on. */
  notifications: Record<string, boolean>;
}

export interface UserSession {
  id: string;
  user_agent: string | null;
  ip_address: string | null;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  current: boolean;
}

export interface SignInProvider {
  id: "google" | "microsoft";
  display_name: string;
  start_url: string;
}

export interface SignupInput {
  email: string;
  password: string;
  display_name: string;
}

export interface LoginInput {
  email: string;
  password: string;
}

export interface ChangePasswordInput {
  current_password: string;
  new_password: string;
}

export interface UpdateProfileInput {
  display_name?: string;
  avatar_url?: string | null;
  notifications?: Record<string, boolean>;
}

// --- notes (mirrors apps/api/app/schemas/notes.py) ---------------------------------------------

/** TipTap/ProseMirror JSON node. */
export interface TipTapNode {
  type: string;
  attrs?: Record<string, unknown>;
  content?: TipTapNode[];
  marks?: { type: string; attrs?: Record<string, unknown> }[];
  text?: string;
}

/** TipTap/ProseMirror JSON document (root node). */
export type TipTapDoc = TipTapNode & { type: "doc" };

export interface Tag {
  id: string;
  name: string;
  color: string | null;
  note_count: number;
}

export interface Folder {
  id: string;
  name: string;
  parent_id: string | null;
  position: number;
  note_count: number;
  created_at: string;
  updated_at: string;
}

export type NoteColor = "default" | "cream" | "yellow" | "green" | "blue" | "purple" | "rose";
export type CollaboratorRole = "viewer" | "editor";
export type NoteAccess = "owner" | "editor" | "viewer";

export interface Collaborator {
  id: string;
  email: string;
  role: CollaboratorRole;
  user_id: string | null;
  display_name: string | null;
  created_at: string;
}

export interface NoteVersion {
  id: string;
  note_version: number;
  title: string;
  plain_text: string;
  reason: "edit" | "before_restore" | string;
  created_at: string;
}

export interface NoteVersionDetail extends NoteVersion {
  content_json: TipTapDoc;
}

export interface NoteSummary {
  id: string;
  title: string;
  excerpt: string;
  folder_id: string | null;
  tags: Tag[];
  is_favorite: boolean;
  archived_at: string | null;
  deleted_at: string | null;
  version: number;
  color: NoteColor;
  reminder_at: string | null;
  checklist: { done: number; total: number } | null;
  shared: boolean;
  access: NoteAccess;
  created_at: string;
  /** Last real edit (title, body or metadata). Opening/reading a note never changes it. */
  updated_at: string;
}

export interface Note extends NoteSummary {
  content_json: TipTapDoc;
  plain_text: string;
  summary: string | null;
  metadata: Record<string, unknown>;
  collaborators: Collaborator[];
}

export type NoteView = "active" | "favorites" | "archived" | "trash" | "shared" | "all";

export interface NoteListParams {
  view?: NoteView;
  folder_id?: string;
  tag_id?: string;
  q?: string;
  cursor?: string;
  limit?: number;
}

export interface NoteCreateInput {
  title?: string;
  content_json?: TipTapDoc;
  folder_id?: string | null;
  tag_ids?: string[];
}

export interface NoteUpdateInput {
  color?: NoteColor;
  reminder_at?: string | null;
  clear_reminder?: boolean;
  title?: string;
  content_json?: TipTapDoc;
  folder_id?: string;
  clear_folder?: boolean;
  tag_ids?: string[];
  is_favorite?: boolean;
  archived?: boolean;
  expected_version?: number;
}

export interface SearchHit {
  source: string; // "notely" or a provider id
  kind: string;
  id: string;
  title: string;
  snippet: string;
  url: string | null;
  score: number;
  updated_at: string | null;
}

export interface SearchSource {
  source: string;
  ok: boolean;
  count: number;
  error: string | null;
}

export interface SearchResponse {
  query: string;
  hits: SearchHit[];
  sources: SearchSource[];
}

// --- tasks & AI (mirrors apps/api/app/schemas/{tasks,ai}.py) -----------------------------------

export type TaskPriority = "none" | "low" | "medium" | "high";
export type TaskStatus = "open" | "done";

export interface Task {
  id: string;
  note_id: string | null;
  title: string;
  description: string | null;
  due_date: string | null;
  /** "HH:MM:SS" in `timezone`; null means all day. */
  due_time: string | null;
  timezone: string | null;
  priority: TaskPriority;
  status: TaskStatus;
  source: "manual" | "ai";
  external_provider: string | null;
  external_task_id: string | null;
  calendar_id: string | null;
  calendar_event_id: string | null;
  calendar_event_url: string | null;
  calendar_synced_at: string | null;
  calendar_error: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskCreateInput {
  title: string;
  description?: string | null;
  due_date?: string | null;
  due_time?: string | null;
  timezone?: string | null;
  priority?: TaskPriority;
  note_id?: string | null;
  source?: "manual" | "ai";
}

export type RiskLevel = "read" | "write" | "external_communication" | "destructive";
export type RunStatus = "queued" | "running" | "waiting_for_approval" | "completed" | "failed" | "cancelled";

export interface AISource {
  provider: string;
  object_id: string;
  title: string;
  url: string | null;
  /** When the agent fetched it (PRD 26). */
  retrieved_at?: string;
}

export type VerificationStatus = "verified" | "unverified" | "failed";

export interface Verification {
  status: VerificationStatus;
  detail: string;
}

export type PlanStepKind = "read" | "propose" | "verify" | "answer";
export type PlanStepStatus = "pending" | "active" | "waiting" | "done" | "skipped";

export interface PlanStep {
  title: string;
  kind: PlanStepKind;
  tools: string[];
  status: PlanStepStatus;
}

export interface AIPlan {
  goal: string;
  steps: PlanStep[];
}

export interface AIStep {
  call_id: string;
  tool: string;
  label: string;
  status: "running" | "completed" | "failed";
  result_preview?: string;
  verification?: Verification;
}

export interface AIThread {
  id: string;
  title: string;
  note_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface AIMessage {
  id: string;
  role: "user" | "assistant" | "tool" | "system";
  content: string;
  sources: AISource[] | null;
  run_id: string | null;
  created_at: string;
  /** Execution metadata of the run that produced this message (client-side only). */
  steps?: AIStep[];
  plan?: AIPlan | null;
}

export interface AIToolCall {
  id: string;
  call_id: string;
  tool_name: string;
  provider: string;
  risk_level: RiskLevel;
  arguments: Record<string, unknown>;
  status: "proposed" | "approved" | "rejected" | "executed" | "failed";
  error: string | null;
  verification: Verification | null;
  executed_at: string | null;
}

export interface AIApproval {
  id: string;
  status: "pending" | "approved" | "rejected" | "expired";
  tool_call_ids: string[];
  created_at: string;
  decided_at: string | null;
}

export interface AIRun {
  id: string;
  thread_id: string;
  status: RunStatus;
  model: string | null;
  provider: string | null;
  token_usage: Record<string, number>;
  steps: { call_id?: string; tool?: string; label?: string; status?: string; type?: string; verification?: Verification }[];
  plan: AIPlan | null;
  sources: AISource[];
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  tool_calls: AIToolCall[];
  approvals: AIApproval[];
}

export interface AIThreadDetail {
  thread: AIThread;
  messages: AIMessage[];
  active_run: AIRun | null;
}

export interface AIProposal {
  call_id: string;
  tool_name: string;
  provider: string;
  risk: RiskLevel;
  summary: string;
  arguments: Record<string, unknown>;
}

/** Events streamed by POST /ai/chat and /ai/approve. */
export type AIChatEvent =
  | { type: "run"; run_id: string; thread_id: string; status: RunStatus }
  | { type: "token"; text: string }
  | { type: "step"; call_id: string; tool: string; label: string; status: "running" | "completed" | "failed"; result_preview?: string }
  | { type: "plan"; call_id: string; goal: string; steps: PlanStep[] }
  | { type: "verification"; call_id: string; status: VerificationStatus; detail: string }
  | { type: "approval_required"; approval_id: string; run_id: string; proposals: AIProposal[] }
  | { type: "message"; message_id: string; content: string; sources: AISource[] }
  | { type: "done"; run_id: string; status: RunStatus; usage: Record<string, number> }
  | { type: "error"; code: string; message: string; details?: Record<string, unknown> };

export type NoteAIAction = "summarize" | "improve" | "key_points" | "extract_tasks" | "custom";

export interface ExtractedTask {
  title: string;
  due_date: string | null;
  priority: TaskPriority;
}

/** Events streamed by POST /ai/actions. */
export type NoteActionEvent =
  | { type: "start"; action: NoteAIAction; note_id: string }
  | { type: "token"; text: string }
  | { type: "tasks"; tasks: ExtractedTask[] }
  | { type: "done"; content: string; action: NoteAIAction }
  | { type: "error"; code: string; message: string; details?: Record<string, unknown> };

export interface AIPreferences {
  model: string | null;
  summary_length: "short" | "medium" | "long";
  confirm_reads: boolean;
}

export interface UserModel {
  provider: string;
  model: string;
  base_url: string | null;
  key_hint: string;
  enabled: boolean;
  verified_at: string | null;
  last_error: string | null;
}

export interface UserModelInput {
  provider: string;
  model: string;
  base_url?: string | null;
  /** Write-only; omit or send "" to keep the stored key. */
  api_key?: string | null;
  enabled: boolean;
}

export interface UserModelProvider {
  id: string;
  label: string;
  key_placeholder: string;
  docs_url: string;
  models: string[];
  needs_base_url: boolean;
  default_base_url: string | null;
}

export interface ModelTestResult {
  ok: boolean;
  detail: string;
  latency_ms: number | null;
}

export interface AISettings {
  provider: string;
  models: { id: string; label: string }[];
  preferences: AIPreferences;
  tools: { name: string; risk: RiskLevel; provider: string; description: string }[];
  user_model: UserModel | null;
  user_model_providers: UserModelProvider[];
  encryption_available: boolean;
}

export interface AuditEvent {
  id: string;
  provider: string;
  action: string;
  tool_name: string | null;
  risk_level: RiskLevel;
  status: string;
  run_id: string | null;
  request_metadata: Record<string, unknown>;
  created_at: string;
}

// --- integrations (mirrors apps/api/app/schemas/integrations.py) --------------------------------

export type ConnectionStatus =
  | "pending"
  | "connecting"
  | "connected"
  | "syncing"
  | "needs_attention"
  | "expired"
  | "error"
  | "disconnected";

export interface Connection {
  id: string;
  provider: string;
  auth_type: "oauth2" | "mcp";
  status: ConnectionStatus;
  external_account_id: string | null;
  external_account_name: string | null;
  scopes: string[];
  config: Record<string, unknown>;
  metadata: Record<string, unknown>;
  token_expires_at: string | null;
  last_sync_at: string | null;
  last_checked_at: string | null;
  last_error: string | null;
  last_error_code: string | null;
  created_at: string;
  updated_at: string;
}

export interface PermissionSpec {
  scope: string;
  label: string;
  description: string;
  required: boolean;
  capability: string | null;
}

export interface ConfigField {
  key: string;
  label: string;
  kind: "text" | "url" | "secret" | "select";
  required: boolean;
  placeholder: string;
  help: string;
  options: { value: string; label: string }[];
}

export type ConnectMethod = "oauth" | "mcp";


export interface Provider {
  id: string;
  name: string;
  category: string;
  description: string;
  logo_url: string | null;
  docs_url: string | null;
  auth: "oauth2";
  capabilities: string[];
  permissions: PermissionSpec[];
  config_fields: ConfigField[];
  /** The vendor's official remote MCP server (one-click OAuth without a per-deployment app). */
  mcp_server_url: string | null;
  /** How this user can connect on this deployment. Empty → nothing is possible yet. */
  connect_methods: ConnectMethod[];
  supports_webhooks: boolean;
  supports_sync: boolean;
  configured: boolean;
  connection: Connection | null;
}

export interface ProviderDetail extends Provider {
  local_item_count: number;
  tools: { name: string; description: string; read_only: boolean; destructive: boolean }[];
}

export interface ConnectionTestResult {
  healthy: boolean;
  steps: { name: string; ok: boolean; detail: string }[];
  connection: Connection;
}

// --- notifications (mirrors apps/api/app/api/v1/notifications.py) ------------------------------

export type NotificationKind =
  | "task_due_soon"
  | "task_overdue"
  | "task_completed"
  | "integration_connected"
  | "integration_disconnected"
  | "integration_auth_required"
  | "calendar_synced"
  | "calendar_sync_failed"
  | "note_reminder"
  | "note_shared";

export interface AppNotification {
  id: string;
  kind: NotificationKind;
  title: string;
  body: string | null;
  href: string | null;
  read_at: string | null;
  created_at: string;
}

export interface NotificationsResponse {
  items: AppNotification[];
  unread: number;
}

export interface CalendarStatus {
  connected: boolean;
  healthy: boolean;
  can_write: boolean;
  account: string | null;
  status: string | null;
}
