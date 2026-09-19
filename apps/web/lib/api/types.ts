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
