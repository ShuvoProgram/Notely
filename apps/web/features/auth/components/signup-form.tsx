"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";

import { FormField } from "@/components/forms/form-field";
import { Button } from "@/components/ui/button";
import { AuthFormError } from "@/features/auth/components/auth-form-error";
import { SignInProviderButtons } from "@/features/auth/components/sign-in-provider-buttons";
import { useSignup } from "@/features/auth/hooks";
import { PASSWORD_MIN, signupSchema, type SignupValues } from "@/features/auth/schemas";
import { ApiError } from "@/lib/api/client";

export function SignupForm() {
  const signup = useSignup();
  const params = useSearchParams();
  // An invitation link lands here with the invited address and where to go afterwards.
  const next = params.get("next");
  const form = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
    defaultValues: { display_name: "", email: params.get("email") ?? "", password: "" },
  });

  const onSubmit = (values: SignupValues) =>
    signup.mutate(values, {
      onError: (error) => {
        // Surface server-side field errors inline instead of only in the banner.
        if (error instanceof ApiError) {
          for (const [field, messages] of Object.entries(error.fieldErrors)) {
            if (field in values) {
              form.setError(field as keyof SignupValues, { message: messages[0] });
            }
          }
        }
      },
    });

  const bannerError =
    signup.error instanceof ApiError && Object.keys(signup.error.fieldErrors).length > 0
      ? null
      : signup.error;

  return (
    <form noValidate aria-label="Create account" className="space-y-5" onSubmit={form.handleSubmit(onSubmit)}>
      <AuthFormError error={bannerError} />
      <FormField
        label="Name"
        autoComplete="name"
        autoFocus
        error={form.formState.errors.display_name?.message}
        {...form.register("display_name")}
      />
      <FormField
        label="Email"
        type="email"
        autoComplete="email"
        error={form.formState.errors.email?.message}
        {...form.register("email")}
      />
      <FormField
        label="Password"
        type="password"
        autoComplete="new-password"
        hint={`At least ${PASSWORD_MIN} characters. A short sentence works well.`}
        error={form.formState.errors.password?.message}
        {...form.register("password")}
      />
      <p className="text-xs text-muted-foreground">
        By creating an account you agree to the{" "}
        <Link href="/terms-and-conditions" className="text-foreground underline-offset-4 hover:underline">
          Terms &amp; Conditions
        </Link>{" "}
        and{" "}
        <Link href="/privacy-policy" className="text-foreground underline-offset-4 hover:underline">
          Privacy Policy
        </Link>
        .
      </p>
      <Button type="submit" className="w-full" disabled={signup.isPending}>
        {signup.isPending ? "Creating account…" : "Create account"}
      </Button>
      <SignInProviderButtons />
      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href={next ? `/login?next=${encodeURIComponent(next)}` : "/login"} className="text-foreground underline-offset-4 hover:underline">
          Sign in
        </Link>
      </p>
    </form>
  );
}
