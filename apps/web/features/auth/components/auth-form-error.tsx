import { AlertCircle } from "lucide-react";

import { ApiError } from "@/lib/api/client";

const MESSAGES: Record<string, string> = {
  INVALID_CREDENTIALS: "Incorrect email or password.",
  EMAIL_TAKEN: "An account with this email already exists.",
  RATE_LIMITED: "Too many attempts. Please wait a minute and try again.",
  CSRF_ORIGIN_REJECTED: "This request was blocked for security reasons. Reload and try again.",
  oauth_denied: "Sign-in was cancelled before access was granted.",
  oauth_failed: "Authorization failed. Your access wasn't granted.",
  oauth_expired: "That sign-in link expired or was already used. Please try again.",
  session_expired: "Your session ended before the connection finished. Sign in and connect again.",
};

export function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    return MESSAGES[error.code] ?? error.message;
  }
  if (typeof error === "string") return MESSAGES[error] ?? "Something went wrong.";
  return "We couldn't reach Notely. Check your connection and try again.";
}

export function AuthFormError({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-foreground"
    >
      <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
      <span>{messageFor(error)}</span>
    </div>
  );
}
