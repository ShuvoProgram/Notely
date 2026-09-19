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
  created_at: string;
  updated_at: string;
}

export interface Note extends NoteSummary {
  content_json: TipTapDoc;
  plain_text: string;
  summary: string | null;
  metadata: Record<string, unknown>;
}

export type NoteView = "active" | "favorites" | "archived" | "trash" | "all";

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
  source: "notely";
  kind: "note";
  id: string;
  title: string;
  snippet: string;
  url: string;
  score: number;
  updated_at: string;
}

export interface SearchResponse {
  query: string;
  hits: SearchHit[];
  sources: string[];
}
