"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";

import { AuthField, PasswordField } from "@/features/auth/components/auth-fields";
import { AuthFormError } from "@/features/auth/components/auth-form-error";
import { AuthHeading, AuthSubmit } from "@/features/auth/components/auth-ui";
import { SignInProviderButtons } from "@/features/auth/components/sign-in-provider-buttons";
import { useSignup } from "@/features/auth/hooks";
import { signupSchema, type SignupValues } from "@/features/auth/schemas";
import { ApiError } from "@/lib/api/client";

export function SignupForm() {
  const signup = useSignup();
  const params = useSearchParams();
  // An invitation link lands here with the invited address and where to go afterwards.
  const next = params.get("next");
  const loginHref = next ? `/login?next=${encodeURIComponent(next)}` : "/login";
  const form = useForm<SignupValues>({
    resolver: zodResolver(signupSchema),
    mode: "onTouched",
    defaultValues: { display_name: "", email: params.get("email") ?? "", password: "" },
  });
  const { errors, dirtyFields, isSubmitted } = form.formState;
  // Don't flag a field just for being left empty: errors show once there's input or after submit.
  // (Showing one on blur would also shift the layout under a click on a nearby link.)
  const shown = (name: keyof SignupValues) => (isSubmitted || dirtyFields[name] || errors[name]?.type === "taken" ? errors[name]?.message : undefined);

  const onSubmit = (values: SignupValues) =>
    signup.mutate(values, {
      onError: (error) => {
        if (!(error instanceof ApiError)) return;
        // An existing address belongs on the email field, with a way forward.
        if (error.code === "EMAIL_TAKEN") {
          form.setError("email", { type: "taken", message: "An account with this email already exists." }, { shouldFocus: true });
          return;
        }
        // Surface server-side field errors inline instead of only in the banner.
        for (const [field, messages] of Object.entries(error.fieldErrors)) {
          if (field in values) form.setError(field as keyof SignupValues, { message: messages[0] });
        }
      },
    });

  // Field-level problems are shown on their fields; the banner is for everything else
  // (rate limits, network trouble, unexpected server errors).
  const bannerError =
    signup.error instanceof ApiError && (signup.error.code === "EMAIL_TAKEN" || Object.keys(signup.error.fieldErrors).length > 0) ? null : signup.error;

  // A field "looks good" once the person has left it and it passes validation.
  const ok = (name: keyof SignupValues) => Boolean(dirtyFields[name]) && !errors[name] && form.getFieldState(name).isTouched;

  return (
    <>
      <AuthHeading title="Create your workspace">Organise your notes, tasks and work in one place.</AuthHeading>
      <form noValidate aria-label="Create account" className="space-y-5" onSubmit={form.handleSubmit(onSubmit)}>
        <AuthFormError error={bannerError} />
        <AuthField label="Name" autoComplete="name" autoFocus placeholder="Alex Morgan" error={shown("display_name")} valid={ok("display_name")} {...form.register("display_name")} />
        <AuthField
          label="Email"
          type="email"
          autoComplete="email"
          inputMode="email"
          placeholder="you@company.com"
          error={shown("email")}
          valid={ok("email")}
          errorAction={
            errors.email?.type === "taken" ? (
              <p className="text-[13px] text-muted-foreground">
                Is it yours?{" "}
                <Link href={loginHref} className="font-bold text-foreground underline underline-offset-4">
                  Sign in instead
                </Link>
              </p>
            ) : null
          }
          {...form.register("email")}
        />
        <PasswordField label="Password" autoComplete="new-password" requirements error={shown("password")} {...form.register("password")} />
        <AuthSubmit pending={signup.isPending} done={signup.isSuccess} pendingLabel="Creating your workspace…" doneLabel="Workspace ready">
          Create account
        </AuthSubmit>
        <p className="text-center text-xs leading-relaxed text-muted-foreground">
          By creating an account you agree to the{" "}
          <Link href="/terms-and-conditions" className="text-foreground underline underline-offset-4">
            Terms &amp; Conditions
          </Link>{" "}
          and{" "}
          <Link href="/privacy-policy" className="text-foreground underline underline-offset-4">
            Privacy Policy
          </Link>
          .
        </p>
      </form>
      <div className="mt-6">
        <SignInProviderButtons />
      </div>
      <p className="mt-8 text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href={loginHref} className="font-bold text-foreground underline-offset-4 hover:underline">
          Sign in
        </Link>
      </p>
    </>
  );
}
