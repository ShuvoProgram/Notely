"use client";

import { ShieldCheck } from "@/components/icons";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { EmptyState } from "@/components/layout/empty-state";
import { Button } from "@/components/ui/button";
import { authApi } from "@/features/auth/api";

/** Admin access needs a recent sign-in (ADMIN_SESSION_MAX_AGE_HOURS). Sign out, then back in. */
export function AdminReauth({ reason }: { reason?: "reauth" | "two_factor" }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const signOut = useMutation({
    mutationFn: authApi.logout,
    onSettled: () => {
      queryClient.clear();
      router.push("/login?next=/admin");
      router.refresh();
    },
  });
  const twoFactor = reason === "two_factor";
  return (
    <div className="glass mx-auto mt-10 max-w-lg rounded-2xl">
      <EmptyState
        icon={ShieldCheck}
        tone="ai"
        title={twoFactor ? "Turn on two-factor authentication" : "Sign in again to continue"}
        description={
          twoFactor
            ? "This deployment requires two-factor authentication for the admin area. Turn it on in your security settings, then come back."
            : "For your security, the admin area needs a recent sign-in. Your workspace session is unaffected until you sign out."
        }
        action={
          twoFactor ? (
            <Button onClick={() => router.push("/app/settings/security")}>Open security settings</Button>
          ) : (
            <Button onClick={() => signOut.mutate()} disabled={signOut.isPending}>
              Sign in again
            </Button>
          )
        }
      />
    </div>
  );
}
