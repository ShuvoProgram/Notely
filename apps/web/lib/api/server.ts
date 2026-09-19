import "server-only";

import { cookies } from "next/headers";

import { ApiError, apiRequest, type RequestOptions } from "@/lib/api/client";
import type { User } from "@/lib/api/types";

/** Where server components reach FastAPI directly (inside Docker: http://api:8000). */
function internalBase(): string {
  const base = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
  return `${base.replace(/\/$/, "")}/api/v1`;
}

/** Server-side request that forwards the caller's session cookie. */
export async function serverApi<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const cookieStore = await cookies();
  const cookieHeader = cookieStore
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join("; ");
  return apiRequest<T>(path, {
    ...options,
    baseUrl: internalBase(),
    headers: { ...(options.headers ?? {}), ...(cookieHeader ? { Cookie: cookieHeader } : {}) },
  });
}

/** Returns the signed-in user or null; never throws for a missing/expired session. */
export async function getCurrentUser(): Promise<User | null> {
  try {
    return await serverApi<User>("/users/me");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}
