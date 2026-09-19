import type { Metadata } from "next";

import { SignupForm } from "@/features/auth/components/signup-form";

export const metadata: Metadata = { title: "Create account" };

export default function SignupPage() {
  return (
    <>
      <h1 className="mb-1 text-xl font-semibold tracking-tight">Create your workspace</h1>
      <p className="mb-6 text-sm text-muted-foreground">Free while in preview. No card needed.</p>
      <SignupForm />
    </>
  );
}
