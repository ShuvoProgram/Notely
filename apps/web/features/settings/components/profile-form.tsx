"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { FormField } from "@/components/forms/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { useCurrentUser, useUpdateProfile } from "@/features/auth/hooks";
import { AvatarUpload } from "@/features/settings/components/avatar-upload";
import { profileSchema, type ProfileValues } from "@/features/auth/schemas";

export function ProfileForm() {
  const { data: user, isPending } = useCurrentUser();
  const update = useUpdateProfile();
  const form = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    values: user ? { display_name: user.display_name } : undefined,
    defaultValues: { display_name: "" },
  });

  if (isPending || !user) {
    return <Skeleton className="h-48 w-full rounded-xl" />;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>How you appear across Notely.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <AvatarUpload user={user} />
        <form
          noValidate
          className="space-y-5"
          onSubmit={form.handleSubmit((values) =>
            update.mutate(values, {
              onSuccess: () => toast.success("Profile updated"),
              onError: (error) => toast.error(messageFor(error)),
            }),
          )}
        >
          <FormField
            label="Display name"
            autoComplete="name"
            error={form.formState.errors.display_name?.message}
            {...form.register("display_name")}
          />
          <FormField label="Email" type="email" value={user.email} readOnly disabled hint="Your email is used to sign in and can't be changed here." />
          <Button type="submit" disabled={update.isPending || !form.formState.isDirty}>
            {update.isPending ? "Saving…" : "Save changes"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
