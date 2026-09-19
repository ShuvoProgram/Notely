"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useForm } from "react-hook-form";

import { FormField } from "@/components/forms/form-field";
import { Button } from "@/components/ui/button";
import { AuthFormError } from "@/features/auth/components/auth-form-error";
import { SignInProviderButtons } from "@/features/auth/components/sign-in-provider-buttons";
import { useLogin } from "@/features/auth/hooks";
import { loginSchema, type LoginValues } from "@/features/auth/schemas";

export function LoginForm({ initialError }: { initialError?: string }) {
  const login = useLogin();
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  const error = login.error ?? (initialError && !form.formState.isSubmitted ? initialError : null);

  return (
    <form
      noValidate
      className="space-y-5"
      onSubmit={form.handleSubmit((values) => login.mutate(values))}
    >
      <AuthFormError error={error} />
      <FormField
        label="Email"
        type="email"
        autoComplete="email"
        autoFocus
        error={form.formState.errors.email?.message}
        {...form.register("email")}
      />
      <FormField
        label="Password"
        type="password"
        autoComplete="current-password"
        error={form.formState.errors.password?.message}
        {...form.register("password")}
      />
      <Button type="submit" className="w-full" disabled={login.isPending}>
        {login.isPending ? "Signing in…" : "Sign in"}
      </Button>
      <SignInProviderButtons />
      <p className="text-center text-sm text-muted-foreground">
        New to Notely?{" "}
        <Link href="/signup" className="text-foreground underline-offset-4 hover:underline">
          Create an account
        </Link>
      </p>
    </form>
  );
}
