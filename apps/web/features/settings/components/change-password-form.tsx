"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { FormField } from "@/components/forms/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { useChangePassword, useCurrentUser } from "@/features/auth/hooks";
import { changePasswordSchema, PASSWORD_MIN, type ChangePasswordValues } from "@/features/auth/schemas";
import { ApiError } from "@/lib/api/client";

export function ChangePasswordForm() {
  const { data: user } = useCurrentUser();
  const change = useChangePassword();
  const form = useForm<ChangePasswordValues>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: { current_password: "", new_password: "", confirm_password: "" },
  });

  if (user && !user.has_password) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Password</CardTitle>
          <CardDescription>
            This account signs in with {user.email_verified ? "a connected provider" : "an external provider"} and has no
            password.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Change password</CardTitle>
        <CardDescription>Changing your password signs out every other device.</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          noValidate
          className="space-y-5"
          onSubmit={form.handleSubmit((values) =>
            change.mutate(
              { current_password: values.current_password, new_password: values.new_password },
              {
                onSuccess: () => {
                  form.reset();
                  toast.success("Password changed");
                },
                onError: (error) => {
                  if (error instanceof ApiError && error.fieldErrors.current_password) {
                    form.setError("current_password", { message: "Incorrect password" });
                    return;
                  }
                  if (error instanceof ApiError && error.fieldErrors.new_password) {
                    form.setError("new_password", { message: error.fieldErrors.new_password[0] });
                    return;
                  }
                  toast.error(messageFor(error));
                },
              },
            ),
          )}
        >
          <FormField
            label="Current password"
            type="password"
            autoComplete="current-password"
            error={form.formState.errors.current_password?.message}
            {...form.register("current_password")}
          />
          <FormField
            label="New password"
            type="password"
            autoComplete="new-password"
            hint={`At least ${PASSWORD_MIN} characters.`}
            error={form.formState.errors.new_password?.message}
            {...form.register("new_password")}
          />
          <FormField
            label="Confirm new password"
            type="password"
            autoComplete="new-password"
            error={form.formState.errors.confirm_password?.message}
            {...form.register("confirm_password")}
          />
          <Button type="submit" disabled={change.isPending}>
            {change.isPending ? "Updating…" : "Update password"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
