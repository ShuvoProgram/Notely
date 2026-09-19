import type { Metadata } from "next";

import { LoginForm } from "@/features/auth/components/login-form";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const error = typeof params.error === "string" ? params.error : undefined;
  return (
    <>
      <h1 className="mb-1 text-xl font-semibold tracking-tight">Welcome back</h1>
      <p className="mb-6 text-sm text-muted-foreground">Sign in to your workspace.</p>
      <LoginForm initialError={error} />
    </>
  );
}
