"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { AlertTriangle, Loader2, LogOut, RefreshCw, UserPlus } from "@/components/icons";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from "@/components/ui/select";
import { messageFor } from "@/features/auth/components/auth-form-error";
import { useCurrentUser } from "@/features/auth/hooks";
import { notesApi } from "@/features/notes/api";
import { noteKeys } from "@/features/notes/hooks";
import { ApiError } from "@/lib/api/client";
import type { Collaborator, CollaboratorRole, Note } from "@/lib/api/types";
import { playSfx } from "@/lib/sfx/player";
import { cn } from "@/lib/utils";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const REMOVE = "__remove__";

function initials(name: string | null | undefined, email: string): string {
  const source = (name || email).trim();
  const parts = source.split(/[\s@.]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

function statusLine(c: Collaborator): { text: string; tone?: "warning" } {
  if (c.status === "accepted") return { text: c.email };
  if (c.status === "expired") return { text: "Invitation expired · resend to give access", tone: "warning" };
  return { text: "Invitation pending · they get access when they sign up with this email" };
}

/**
 * Share a note, Keep-style: type a person, pick "Can view" or "Can edit", press Share. People with
 * a Notely account get access immediately (the note appears under Shared for them); anyone else
 * gets an emailed invitation that turns into access when they sign up with that address.
 * The owner changes permissions or removes access per person; guests can see who's on the note
 * and leave it. Every rule is enforced by the API; this dialog only reflects it.
 */
export function ShareDialog({ note, open, onOpenChange }: { note: Note; open: boolean; onOpenChange: (o: boolean) => void }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const { data: me } = useCurrentUser();
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState<CollaboratorRole>("viewer");
  const [emailError, setEmailError] = React.useState<string | null>(null);
  const [lastDeliveryError, setLastDeliveryError] = React.useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = React.useState<Collaborator | null>(null);
  const [confirmLeave, setConfirmLeave] = React.useState(false);
  const [suggestOpen, setSuggestOpen] = React.useState(false);
  const [highlight, setHighlight] = React.useState(0);
  const owner = note.access === "owner";

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: noteKeys.detail(note.id) });
    void queryClient.invalidateQueries({ queryKey: ["notes", "list"] });
  };

  // Who has access changes from elsewhere too (an invitee signs up, someone leaves): show the
  // current list whenever the dialog opens rather than what was cached when the note loaded.
  React.useEffect(() => {
    if (open) void queryClient.invalidateQueries({ queryKey: noteKeys.detail(note.id) });
  }, [open, note.id, queryClient]);

  const typed = email.trim().toLowerCase();
  const suggestions = useQuery({
    queryKey: ["notes", "share-suggestions", typed],
    queryFn: () => notesApi.shareSuggestions(typed),
    enabled: open && owner,
    staleTime: 60_000,
  });
  const already = new Set(note.collaborators.map((c) => c.email));
  const options = (suggestions.data ?? []).filter((p) => !already.has(p.email)).slice(0, 5);
  const showSuggestions = suggestOpen && options.length > 0;

  const invite = useMutation({
    mutationFn: (input: { email: string; role: CollaboratorRole; resend?: boolean }) => notesApi.invite(note.id, input),
    onSuccess: ({ collaborator, delivery }, input) => {
      refresh();
      setEmail("");
      playSfx("success");
      const name = collaborator.display_name ?? collaborator.email;
      if (collaborator.status === "accepted") {
        setLastDeliveryError(null);
        toast.success(input.resend ? `Reminded ${name}` : `Shared with ${name}`, {
          description: "It's in their Shared notes now.",
        });
      } else if (delivery.sent) {
        setLastDeliveryError(null);
        toast.success(input.resend ? "Invitation re-sent" : "Invitation sent", {
          description: `${collaborator.email} gets access when they sign up with this email.`,
        });
      } else {
        // Server set-up details (SMTP settings) are for admins, not for the person sharing.
        const raw = delivery.error ?? "";
        setLastDeliveryError(
          /smtp|not configured/i.test(raw)
            ? "Email isn't set up on this Notely server, so no email went out. They still get access as soon as they sign up with this address — you may want to tell them yourself."
            : raw || "The email could not be sent.",
        );
        toast.message("Invitation saved, but the email wasn't sent", {
          description: `${collaborator.email} still gets access when they sign up with this address.`,
          duration: 8000,
        });
      }
    },
    onError: (e) => {
      playSfx("error");
      if (e instanceof ApiError && e.code === "INVITE_ALREADY_SENT") toast.message("Already invited", { description: "Use Resend next to their name if the email didn't arrive." });
      else if (e instanceof ApiError && e.code === "INVITE_ALREADY_ACCEPTED") toast.message("They already have access", { description: "Change their permission from the list." });
      else if (e instanceof ApiError && e.fieldErrors.email) setEmailError(e.fieldErrors.email[0] ?? "Invalid email");
      else toast.error(messageFor(e));
    },
  });
  const change = useMutation({
    mutationFn: ({ id, role }: { id: string; role: CollaboratorRole }) => notesApi.updateCollaborator(note.id, id, role),
    onSuccess: (c) => {
      refresh();
      toast.success(`${c.display_name ?? c.email} ${c.role === "editor" ? "can edit" : "can view"}`);
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  const remove = useMutation({
    mutationFn: (c: Collaborator) => notesApi.removeCollaborator(note.id, c.id),
    onSuccess: (_, c) => {
      refresh();
      setConfirmRemove(null);
      toast.success(`Removed ${c.display_name ?? c.email}`, { description: "They lost access immediately." });
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  const leave = useMutation({
    mutationFn: () => notesApi.leaveMany([note.id]),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: noteKeys.detail(note.id) });
      void queryClient.invalidateQueries({ queryKey: ["notes", "list"] });
      toast.success("You left the note");
      onOpenChange(false);
      router.push("/app/notes?view=shared");
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  const pick = (value: string) => {
    setEmail(value);
    setSuggestOpen(false);
    setEmailError(null);
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (showSuggestions && options[highlight] && !EMAIL.test(typed)) {
      pick(options[highlight].email);
      return;
    }
    if (!EMAIL.test(typed)) {
      setEmailError("Enter an email address, or pick someone you've shared with before.");
      return;
    }
    if (me && typed === me.email.toLowerCase()) {
      setEmailError("That's you — you already own this note.");
      return;
    }
    if (already.has(typed)) {
      setEmailError("They're already on this note. Change their permission below.");
      return;
    }
    setEmailError(null);
    setSuggestOpen(false);
    invite.mutate({ email: typed, role });
  };

  const people = note.collaborators;
  const pending = people.filter((c) => c.status !== "accepted");
  const members = people.filter((c) => c.status === "accepted");
  const ownerInfo = note.owner ?? (owner && me ? { id: me.id, display_name: me.display_name, email: me.email } : null);

  const row = (c: Collaborator) => {
    const line = statusLine(c);
    return (
      <li key={c.id} className="flex items-center gap-3 py-2.5">
        <Avatar className="size-9">
          <AvatarFallback className={cn("text-xs", c.status === "accepted" ? "bg-ai-soft text-ai" : "bg-muted text-muted-foreground")}>{initials(c.display_name, c.email)}</AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">
            {c.display_name ?? c.email}
            {me && c.user_id === me.id ? <span className="font-normal text-muted-foreground"> (you)</span> : null}
          </p>
          <p className={cn("truncate text-xs", line.tone === "warning" ? "text-warning" : "text-muted-foreground")}>{line.text}</p>
        </div>
        {owner && c.status !== "accepted" ? (
          <Button
            variant="ghost"
            size="sm"
            aria-label={`Resend invitation to ${c.email}`}
            disabled={invite.isPending}
            onClick={() => invite.mutate({ email: c.email, role: c.role, resend: true })}
            className="text-muted-foreground max-sm:px-1.5"
          >
            <RefreshCw aria-hidden /> <span className="max-sm:hidden">Resend</span>
          </Button>
        ) : null}
        {owner ? (
          <Select
            value={c.role}
            onValueChange={(v) => {
              if (v === REMOVE) setConfirmRemove(c);
              else if (v !== c.role) change.mutate({ id: c.id, role: v as CollaboratorRole });
            }}
          >
            <SelectTrigger aria-label={`Permission for ${c.display_name ?? c.email}`} size="sm" className="w-[6.75rem] shrink-0">
              <SelectValue />
            </SelectTrigger>
            <SelectContent align="end">
              <SelectItem value="viewer">Can view</SelectItem>
              <SelectItem value="editor">Can edit</SelectItem>
              <SelectSeparator />
              <SelectItem value={REMOVE} className="text-destructive focus:text-destructive">
                Remove access
              </SelectItem>
            </SelectContent>
          </Select>
        ) : (
          <span className="shrink-0 text-xs text-muted-foreground">{c.role === "editor" ? "Can edit" : "Can view"}</span>
        )}
      </li>
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Share “{note.title || "Untitled"}”</DialogTitle>
          <DialogDescription>
            {owner ? "People you add can open this note from their Shared list." : "Only the owner can change who has access."}
          </DialogDescription>
        </DialogHeader>

        {owner ? (
          <form className="space-y-1.5" onSubmit={submit} noValidate>
            <div className="flex flex-col gap-2 sm:flex-row">
              <div className="relative min-w-0 flex-1">
                <Input
                  type="email"
                  inputMode="email"
                  autoComplete="off"
                  role="combobox"
                  aria-expanded={showSuggestions}
                  aria-controls="share-suggestions"
                  aria-autocomplete="list"
                  aria-activedescendant={showSuggestions ? `share-opt-${highlight}` : undefined}
                  aria-label="Add people by email"
                  placeholder="Add people by email"
                  value={email}
                  aria-invalid={emailError ? true : undefined}
                  onFocus={() => setSuggestOpen(true)}
                  onBlur={() => setTimeout(() => setSuggestOpen(false), 120)}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setEmailError(null);
                    setSuggestOpen(true);
                    setHighlight(0);
                  }}
                  onKeyDown={(e) => {
                    if (!showSuggestions) return;
                    if (e.key === "ArrowDown") {
                      e.preventDefault();
                      setHighlight((h) => (h + 1) % options.length);
                    } else if (e.key === "ArrowUp") {
                      e.preventDefault();
                      setHighlight((h) => (h - 1 + options.length) % options.length);
                    } else if (e.key === "Escape") {
                      e.stopPropagation();
                      setSuggestOpen(false);
                    }
                  }}
                  className="h-10"
                />
                {showSuggestions ? (
                  <ul id="share-suggestions" role="listbox" aria-label="People you've shared with" className="glass-2 absolute inset-x-0 top-full z-20 mt-1 overflow-hidden rounded-xl p-1 shadow-lg">
                    {options.map((p, i) => (
                      <li
                        key={p.email}
                        id={`share-opt-${i}`}
                        role="option"
                        aria-selected={i === highlight}
                        onMouseDown={(e) => {
                          e.preventDefault();
                          pick(p.email);
                        }}
                        onMouseEnter={() => setHighlight(i)}
                        className={cn("flex cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm", i === highlight && "bg-accent")}
                      >
                        <Avatar className="size-7">
                          <AvatarFallback className="bg-muted text-[10px]">{initials(p.display_name, p.email)}</AvatarFallback>
                        </Avatar>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate">{p.display_name ?? p.email}</span>
                          {p.display_name ? <span className="block truncate text-xs text-muted-foreground">{p.email}</span> : null}
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
              <div className="flex gap-2">
                <Select value={role} onValueChange={(v) => setRole(v as CollaboratorRole)}>
                  <SelectTrigger aria-label="Permission" className="h-10 w-[7.25rem] shrink-0 max-sm:flex-1">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="viewer">Can view</SelectItem>
                    <SelectItem value="editor">Can edit</SelectItem>
                  </SelectContent>
                </Select>
                <Button type="submit" className="h-10 shrink-0 max-sm:flex-1" disabled={!email.trim() || invite.isPending}>
                  {invite.isPending ? <Loader2 className="animate-spin" aria-hidden /> : <UserPlus aria-hidden />} Share
                </Button>
              </div>
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
              <p className="font-medium">The invitation email wasn&apos;t sent</p>
              <p className="break-words text-muted-foreground">{lastDeliveryError}</p>
            </div>
          </div>
        ) : null}

        <section aria-labelledby="share-people">
          <h3 id="share-people" className="text-xs font-medium text-muted-foreground">
            People with access
          </h3>
          <ul className="divide-y divide-glass-border">
            {ownerInfo ? (
              <li className="flex items-center gap-3 py-2.5">
                <Avatar className="size-9">
                  <AvatarFallback className="bg-ai-soft text-xs text-ai">{initials(ownerInfo.display_name, ownerInfo.email)}</AvatarFallback>
                </Avatar>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">
                    {ownerInfo.display_name}
                    {me && ownerInfo.id === me.id ? <span className="font-normal text-muted-foreground"> (you)</span> : null}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">{ownerInfo.email}</p>
                </div>
                <span className="shrink-0 text-xs font-medium text-muted-foreground">Owner</span>
              </li>
            ) : null}
            {members.map(row)}
          </ul>
          {!members.length && owner ? <p className="py-2 text-xs text-muted-foreground">Only you can see this note.</p> : null}
        </section>

        {pending.length ? (
          <section aria-labelledby="share-pending">
            <h3 id="share-pending" className="text-xs font-medium text-muted-foreground">
              Pending invitations
            </h3>
            <ul className="divide-y divide-glass-border">{pending.map(row)}</ul>
          </section>
        ) : null}

        {!owner ? (
          <div className="flex justify-end">
            <Button variant="outline" onClick={() => setConfirmLeave(true)}>
              <LogOut aria-hidden /> Leave note
            </Button>
          </div>
        ) : null}

        <ConfirmDialog
          open={confirmRemove !== null}
          onOpenChange={(o) => !o && setConfirmRemove(null)}
          title={`Remove ${confirmRemove?.display_name ?? confirmRemove?.email ?? ""}?`}
          description={
            confirmRemove?.status === "accepted"
              ? "They lose access to this note right away. Nothing they wrote is removed."
              : "Their invitation link stops working right away."
          }
          confirmLabel="Remove access"
          pending={remove.isPending}
          onConfirm={() => confirmRemove && remove.mutate(confirmRemove)}
        />
        <ConfirmDialog
          open={confirmLeave}
          onOpenChange={setConfirmLeave}
          title="Leave this note?"
          description="It leaves your Shared list. The owner can share it with you again."
          confirmLabel="Leave note"
          pending={leave.isPending}
          onConfirm={() => leave.mutate()}
        />
      </DialogContent>
    </Dialog>
  );
}
