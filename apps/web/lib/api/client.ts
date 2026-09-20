/**
 * Typed fetch client for the Notely API.
 *
 * All requests go through the same-origin `/api/*` path, which Next.js rewrites to FastAPI
 * (see next.config.ts). Same-origin means the HttpOnly session cookie is sent automatically
 * and never touches JavaScript.
 */

export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown> };
}

export interface ApiSuccess<T> {
  data: T;
  meta: Record<string, unknown>;
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody["error"]) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details ?? {};
  }

  /** Field-level validation messages, when the server provided them. */
  get fieldErrors(): Record<string, string[]> {
    const fields = this.details["fields"];
    return typeof fields === "object" && fields !== null
      ? (fields as Record<string, string[]>)
      : {};
  }
}

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Extra headers, e.g. forwarded cookies on the server. */
  headers?: Record<string, string>;
  /** Absolute base URL for server-side calls; defaults to the same-origin proxy. */
  baseUrl?: string;
}

const DEFAULT_BASE = "/api/v1";

/** Like `apiRequest` but returns the whole `{data, meta}` envelope (for paginated lists). */
export async function apiEnvelope<T, M extends Record<string, unknown> = Record<string, unknown>>(
  path: string,
  options: RequestOptions = {},
): Promise<{ data: T; meta: M }> {
  const { body, headers = {}, baseUrl, ...init } = options;
  const url = `${baseUrl ?? DEFAULT_BASE}${path}`;
  const response = await fetch(url, {
    ...init,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });

  if (response.status === 204) {
    return { data: undefined as T, meta: {} as M };
  }

  let json: unknown = null;
  try {
    json = await response.json();
  } catch {
    // fall through: non-JSON body
  }

  if (!response.ok) {
    const errorBody = (json as ApiErrorBody | null)?.error ?? {
      code: "HTTP_ERROR",
      message: "The request could not be completed.",
      details: {},
    };
    throw new ApiError(response.status, errorBody);
  }

  const envelope = json as ApiSuccess<T>;
  return { data: envelope.data, meta: (envelope.meta ?? {}) as M };
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  return (await apiEnvelope<T>(path, options)).data;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => apiRequest<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: "POST", body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: "PATCH", body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: "PUT", body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: "DELETE" }),
};
