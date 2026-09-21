"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Loader2, Mail, RefreshCw, UserPlus, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { notesApi } from "@/features/notes/api";
import { noteKeys } from "@/features/notes/hooks";
import { ApiError } from "@/lib/api/client";
import type { Collaborator, CollaboratorRole, Note } from "@/lib/api/types";
import { playSfx } from "@/lib/sfx/player";

const ROLE_LABEL: Record<CollaboratorRole, string> = { viewer: "Can view", editor: "Can edit" };
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function statusLine(c: Collaborator): { text: string; tone?: "warning" } {
  if (c.status === "accepted") return { text: c.user_id ? "Has access" : "Accepted" };
  if (c.status === "expired") return { text: "Invitation expired — resend to give access", tone: "warning" };
  return { text: c.user_id ? "Invited — has a Notely account" : "Invited — waiting for them to open the email" };
}

/**
 * Share a note by email. The server creates the invitation and emails a link; the dialog tells
 * the truth about delivery ("Invitation sent" only when the mail actually left, otherwise the
 * server's reason). Roles are viewer / editor; the owner manages access, a guest can only leave.
 */
export function ShareDialog({ note, open, onOpenChange }: { note: Note; open: boolean; onOpenChange: (o: boolean) => void }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState<CollaboratorRole>("viewer");
  const [emailError, setEmailError] = React.useState<string | null>(null);
  const [lastDeliveryError, setLastDeliveryError] = React.useState<string | null>(null);
  const owner = note.access === "owner";
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: noteKeys.detail(note.id) });
    queryClient.invalidateQueries({ queryKey: ["notes", "list"] });
  };

  const invite = useMutation({
    mutationFn: (input: { email: string; role: CollaboratorRole; resend?: boolean }) => notesApi.invite(note.id, input),
    onSuccess: ({ collaborator, delivery }, input) => {
      refresh();
      if (delivery.sent) {
        playSfx("success");
        setEmail("");
        setLastDeliveryError(null);
        toast.success(input.resend ? "Invitation re-sent" : "Invitation sent", { description: `${collaborator.email} will get an email with a link to this note.` });
      } else {
        playSfx("error");
        setLastDeliveryError(delivery.error ?? "The email could not be sent.");
        toast.error("Unable to send invitation", {
          description: collaborator.user_id
            ? "They already have a Notely account, so the note is in their Shared list anyway."
            : "The invitation is saved; they'll also get access if they sign up with this address.",
          duration: 8000,
        });
      }
    },
    onError: (e) => {
      playSfx("error");
      if (e instanceof ApiError && e.code === "INVITE_ALREADY_SENT") toast.message("Invitation already sent", { description: "Use Resend next to their name if it didn't arrive." });
      else if (e instanceof ApiError && e.code === "INVITE_ALREADY_ACCEPTED") toast.message("They already have access", { description: "Change their role from the list instead." });
      else if (e instanceof ApiError && e.fieldErrors.email) setEmailError(e.fieldErrors.email[0] ?? "Invalid email");
      else toast.error(messageFor(e));
    },
  });
  const change = useMutation({
    mutationFn: ({ id, role }: { id: string; role: CollaboratorRole }) => notesApi.updateCollaborator(note.id, id, role),
    onSuccess: refresh,
    onError: (e) => toast.error(messageFor(e)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => notesApi.removeCollaborator(note.id, id),
    onSuccess: refresh,
    onError: (e) => toast.error(messageFor(e)),
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const value = email.trim().toLowerCase();
    if (!EMAIL.test(value)) {
      setEmailError("Enter a valid email address.");
      return;
    }
    setEmailError(null);
    invite.mutate({ email: value, role });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Share “{note.title || "Untitled"}”</DialogTitle>
          <DialogDescription>{owner ? "Invite people by email. Editors can change the note; viewers can only read it." : "You’re a guest on this note. Only the owner can change who has access."}</DialogDescription>
        </DialogHeader>

        {owner ? (
          <form className="space-y-1.5" onSubmit={submit} noValidate>
            <div className="flex gap-2">
              <div className="relative min-w-0 flex-1">
                <Mail className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
                <Input
                  type="email"
                  aria-label="Email address"
                  placeholder="name@company.com"
                  value={email}
                  aria-invalid={emailError ? true : undefined}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setEmailError(null);
                  }}
                  className="pl-8"
                />
              </div>
              <Select value={role} onValueChange={(v) => setRole(v as CollaboratorRole)}>
                <SelectTrigger aria-label="Role" className="w-28 shrink-0">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="viewer">Can view</SelectItem>
                  <SelectItem value="editor">Can edit</SelectItem>
                </SelectContent>
              </Select>
              <Button type="submit" size="icon" aria-label="Invite" disabled={!email.trim() || invite.isPending}>
                {invite.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <UserPlus aria-hidden />}
              </Button>
            </div>
            {emailError ? (
              <p role="alert" className="text-xs text-destructive">
                {emailError}
              </p>
            ) : null}
          </form>
        ) : null}

        {lastDeliveryError ? (
          <div role="alert" className="flex gap-2 rounded-lg border border-warning/40 bg-warning/10 p-3 text-xs">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
            <div className="min-w-0 space-y-1">
              <p className="font-medium">The invitation email was not sent</p>
              <p className="break-words text-muted-foreground">{lastDeliveryError}</p>
            </div>
          </div>
        ) : null}

        <ul className="divide-y divide-glass-border" aria-label="People with access">
          {note.collaborators.length === 0 ? (
            <li className="py-6 text-center text-sm text-muted-foreground">Only you can see this note.</li>
          ) : (
            note.collaborators.map((c) => {
              const line = statusLine(c);
              const resendable = owner && c.status !== "accepted";
              return (
                <li key={c.id} className="flex items-center gap-3 py-2.5">
                  <Avatar className="size-8">
                    <AvatarFallback className="bg-muted text-xs">{c.email.slice(0, 2).toUpperCase()}</AvatarFallback>
                  </Avatar>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm">{c.email}</p>
                    <p className={line.tone === "warning" ? "text-xs text-warning" : "text-xs text-muted-foreground"}>{line.text}</p>
                  </div>
                  {resendable ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Resend invitation to ${c.email}`}
                      disabled={invite.isPending}
                      onClick={() => invite.mutate({ email: c.email, role: c.role, resend: true })}
                      className="text-muted-foreground"
                    >
                      <RefreshCw aria-hidden /> Resend
                    </Button>
                  ) : null}
                  {owner ? (
                    <Select value={c.role} onValueChange={(v) => change.mutate({ id: c.id, role: v as CollaboratorRole })}>
                      <SelectTrigger aria-label={`Role for ${c.email}`} size="sm" className="w-28">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="viewer">Can view</SelectItem>
                        <SelectItem value="editor">Can edit</SelectItem>
                      </SelectContent>
                    </Select>
                  ) : (
                    <Badge variant="outline" className="font-normal">
                      {ROLE_LABEL[c.role]}
                    </Badge>
                  )}
                  {owner ? (
                    <Button variant="ghost" size="icon-sm" aria-label={`Remove ${c.email}`} onClick={() => remove.mutate(c.id)} disabled={remove.isPending} className="text-muted-foreground hover:text-destructive">
                      <X aria-hidden />
                    </Button>
                  ) : null}
                </li>
              );
            })
          )}
        </ul>
        <p className="text-xs text-muted-foreground">Invitations are emailed with a personal link that expires after 7 days. Anyone who signs up with the invited address gets access too. Edits made at the same time are merged last-write-wins for now.</p>
      </DialogContent>
    </Dialog>
  );
}
