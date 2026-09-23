"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import * as React from "react";

import { ShieldCheck } from "@/components/icons";
import { AuthField, PasswordField } from "@/features/auth/components/auth-fields";
import { AuthFormError } from "@/features/auth/components/auth-form-error";
import { AuthHeading, AuthSubmit } from "@/features/auth/components/auth-ui";
import { SignInProviderButtons } from "@/features/auth/components/sign-in-provider-buttons";
import { useLogin } from "@/features/auth/hooks";
import { authApi } from "@/features/auth/api";
import { ApiError } from "@/lib/api/client";
import { loginSchema, type LoginValues } from "@/features/auth/schemas";

export function LoginForm({ initialError }: { initialError?: string }) {
  const login = useLogin();
  const params = useSearchParams();
  const next = params.get("next");
  const twoFactor = params.get("two_factor") === "1";
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    mode: "onTouched",
    defaultValues: { email: "", password: "" },
  });

  if (twoFactor) return <TwoFactorStep next={next} />;

  // An error from the URL (e.g. a cancelled Google sign-in) shows until the form is used.
  const error = login.error ?? (initialError && !form.formState.isSubmitted ? initialError : null);
  const { errors, dirtyFields, isSubmitted } = form.formState;
  // Errors show once there's input or after submit, never just for leaving a field empty.
  const shown = (name: keyof LoginValues) => (isSubmitted || dirtyFields[name] ? errors[name]?.message : undefined);

  return (
    <>
      <AuthHeading title="Welcome back">Sign in to continue to your Notely workspace.</AuthHeading>
      <form noValidate aria-label="Sign in" className="space-y-5" onSubmit={form.handleSubmit((values) => login.mutate(values))}>
        <AuthFormError error={error} />
        <AuthField label="Email" type="email" autoComplete="email" inputMode="email" autoFocus placeholder="you@company.com" error={shown("email")} {...form.register("email")} />
        <PasswordField label="Password" autoComplete="current-password" error={shown("password")} {...form.register("password")} />
        <AuthSubmit pending={login.isPending} done={login.isSuccess} pendingLabel="Signing in…" doneLabel="Signed in">
          Sign in
        </AuthSubmit>
      </form>
      <div className="mt-6">
        <SignInProviderButtons />
      </div>
      <p className="mt-8 text-center text-sm text-muted-foreground">
        Don’t have an account?{" "}
        <Link href={next ? `/signup?next=${encodeURIComponent(next)}` : "/signup"} className="font-bold text-foreground underline-offset-4 hover:underline">
          Sign up
        </Link>
      </p>
    </>
  );
}

/** Second step for accounts with two-factor sign-in: an authenticator or recovery code. */
function TwoFactorStep({ next }: { next: string | null }) {
  const router = useRouter();
  const [code, setCode] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [verifying, setVerifying] = React.useState(false);
  const [done, setDone] = React.useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setVerifying(true);
    setError(null);
    try {
      await authApi.verifyTwoFactor(code);
      setDone(true);
      router.push(next?.startsWith("/app") ? next : "/app");
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "That verification code is not valid.");
    } finally {
      setVerifying(false);
    }
  };

  return (
    <>
      <span className="mb-5 grid size-12 place-items-center rounded-2xl bg-ai/10 text-ai ring-1 ring-ai/25">
        <ShieldCheck className="size-6" aria-hidden />
      </span>
      <AuthHeading title="Two-step verification">Enter the six-digit code from your authenticator app, or one of your recovery codes.</AuthHeading>
      <form noValidate aria-label="Two-step verification" className="space-y-5" onSubmit={submit}>
        <AuthField
          label="Verification code"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          inputMode="numeric"
          autoComplete="one-time-code"
          autoFocus
          placeholder="123 456"
          className="[&_input]:text-center [&_input]:font-mono [&_input]:text-lg [&_input]:tracking-[0.3em]"
          error={error ?? undefined}
        />
        <AuthSubmit pending={verifying} done={done} disabled={!code.trim()} pendingLabel="Verifying…" doneLabel="Verified">
          Verify and continue
        </AuthSubmit>
      </form>
    </>
  );
}
