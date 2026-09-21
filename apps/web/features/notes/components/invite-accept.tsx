"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2, MailX, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { useLogout } from "@/features/auth/hooks";
import { notesApi } from "@/features/notes/api";
import { ApiError } from "@/lib/api/client";
import type { User } from "@/lib/api/types";
import { playSfx } from "@/lib/sfx/player";

/**
 * The invitation link. Explains what was shared and by whom, then routes the visitor to the
 * one action that fits: sign in / create an account (with the invited address), switch
 * account, or accept. Expired and dead links say so instead of failing silently.
 */
export function InviteAccept({ token, user }: { token: string; user: User | null }) {
  const router = useRouter();
  const logout = useLogout();
  const invitation = useQuery({ queryKey: ["invitation", token], queryFn: () => notesApi.invitation(token), retry: false });
  const accept = useMutation({
    mutationFn: () => notesApi.acceptInvitation(token),
    onSuccess: (note) => {
      playSfx("success");
      toast.success("You now have access", { description: note.title || "Untitled" });
      router.push(`/app/notes/${note.id}`);
      router.refresh();
    },
    onError: (e) => {
      playSfx("error");
      toast.error(e instanceof ApiError && e.code === "INVITE_EXPIRED" ? "Invitation expired" : messageFor(e));
    },
  });

  if (invitation.isPending) {
    return (
      <div className="space-y-3" aria-busy>
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-9 w-40" />
      </div>
    );
  }
  if (invitation.error || !invitation.data) {
    return (
      <div className="text-center">
        <MailX className="mx-auto mb-3 size-8 text-muted-foreground" aria-hidden />
        <h1 className="text-lg font-semibold tracking-tight">This invitation link isn’t valid</h1>
        <p className="mt-1 text-sm text-muted-foreground">It may have been used already, replaced by a newer one, or the note was removed. Ask the person who shared it to send it again.</p>
        <Button asChild variant="outline" className="mt-5">
          <Link href={user ? "/app" : "/login"}>{user ? "Go to Notely" : "Sign in"}</Link>
        </Button>
      </div>
    );
  }

  const inv = invitation.data;
  const here = `/invite/${encodeURIComponent(token)}`;
  const access = inv.role === "editor" ? "edit" : "view";

  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-muted-foreground">Shared note</p>
      <h1 className="mt-1 text-xl font-semibold tracking-tight">{inv.note_title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        <span className="text-foreground">{inv.inviter_name}</span> invited <span className="text-foreground">{inv.email}</span> to {access} this note.
      </p>

      {inv.status === "expired" ? (
        <div className="mt-5 rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
          <p className="font-medium">Invitation expired</p>
          <p className="text-muted-foreground">Ask {inv.inviter_name} to resend it from the note’s Share dialog.</p>
        </div>
      ) : !user ? (
        <div className="mt-6 space-y-2">
          <Button asChild className="w-full">
            <Link href={`/login?next=${encodeURIComponent(here)}`}>Sign in to accept</Link>
          </Button>
          <Button asChild variant="outline" className="w-full">
            <Link href={`/signup?next=${encodeURIComponent(here)}&email=${encodeURIComponent(inv.email)}`}>Create an account</Link>
          </Button>
          <p className="pt-1 text-center text-xs text-muted-foreground">Use {inv.email} — the invitation is tied to that address.</p>
        </div>
      ) : user.email.toLowerCase() !== inv.email.toLowerCase() ? (
        <div className="mt-5 space-y-3">
          <div className="flex items-start gap-2 rounded-lg border border-glass-border bg-muted/40 p-3 text-sm">
            <UserRound className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
            <p className="text-muted-foreground">
              You’re signed in as <span className="text-foreground">{user.email}</span>, but this invitation is for <span className="text-foreground">{inv.email}</span>.
            </p>
          </div>
          <Button variant="outline" className="w-full" disabled={logout.isPending} onClick={() => logout.mutate(undefined, { onSettled: () => router.push(`/login?next=${encodeURIComponent(here)}`) })}>
            Switch account
          </Button>
        </div>
      ) : inv.status === "accepted" ? (
        <Button asChild className="mt-6 w-full">
          <Link href={`/app/notes/${inv.note_id}`}>Open the note</Link>
        </Button>
      ) : (
        <div className="mt-6 flex gap-2">
          <Button className="flex-1" disabled={accept.isPending} onClick={() => accept.mutate()}>
            {accept.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null} Accept invitation
          </Button>
          <Button asChild variant="outline">
            <Link href="/app">Not now</Link>
          </Button>
        </div>
      )}
    </div>
  );
}
