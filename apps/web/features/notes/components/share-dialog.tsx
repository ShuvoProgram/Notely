"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Mail, UserPlus, X } from "lucide-react";
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
import type { CollaboratorRole, Note } from "@/lib/api/types";
import { playSfx } from "@/lib/sfx/player";

const ROLE_LABEL: Record<CollaboratorRole, string> = { viewer: "Can view", editor: "Can edit" };

/**
 * Share a note with specific people by email. Roles are viewer / editor; the owner manages
 * access, a guest can only leave. Access is enforced by the API; this dialog is the whole
 * management surface so the editor header stays clean. Live co-editing is not implemented —
 * the model (note_collaborators) is what a realtime layer would key on later.
 */
export function ShareDialog({ note, open, onOpenChange }: { note: Note; open: boolean; onOpenChange: (o: boolean) => void }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState<CollaboratorRole>("viewer");
  const owner = note.access === "owner";
  const refresh = () => queryClient.invalidateQueries({ queryKey: noteKeys.detail(note.id) });

  const invite = useMutation({
    mutationFn: () => notesApi.invite(note.id, { email: email.trim(), role }),
    onSuccess: (c) => {
      playSfx("success");
      setEmail("");
      refresh();
      queryClient.invalidateQueries({ queryKey: ["notes", "list"] });
      toast.success(`Shared with ${c.email}`, { description: c.user_id ? "They can open it now." : "They’ll get access when they sign up with that email." });
    },
    onError: (e) => toast.error(messageFor(e)),
  });
  const change = useMutation({
    mutationFn: ({ id, role }: { id: string; role: CollaboratorRole }) => notesApi.updateCollaborator(note.id, id, role),
    onSuccess: refresh,
    onError: (e) => toast.error(messageFor(e)),
  });
  const remove = useMutation({
    mutationFn: (id: string) => notesApi.removeCollaborator(note.id, id),
    onSuccess: () => {
      refresh();
      queryClient.invalidateQueries({ queryKey: ["notes", "list"] });
    },
    onError: (e) => toast.error(messageFor(e)),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Share “{note.title || "Untitled"}”</DialogTitle>
          <DialogDescription>{owner ? "Invite people by email. Editors can change the note; viewers can only read it." : "You’re a guest on this note. Only the owner can change who has access."}</DialogDescription>
        </DialogHeader>

        {owner ? (
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (email.trim()) invite.mutate();
            }}
          >
            <div className="relative min-w-0 flex-1">
              <Mail className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input type="email" aria-label="Email address" placeholder="name@company.com" value={email} onChange={(e) => setEmail(e.target.value)} className="pl-8" required />
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
          </form>
        ) : null}

        <ul className="divide-y divide-glass-border" aria-label="People with access">
          {note.collaborators.length === 0 ? (
            <li className="py-6 text-center text-sm text-muted-foreground">Only you can see this note.</li>
          ) : (
            note.collaborators.map((c) => (
              <li key={c.id} className="flex items-center gap-3 py-2.5">
                <Avatar className="size-8">
                  <AvatarFallback className="bg-muted text-xs">{c.email.slice(0, 2).toUpperCase()}</AvatarFallback>
                </Avatar>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">{c.email}</p>
                  <p className="text-xs text-muted-foreground">{c.user_id ? "Has a Notely account" : "Invited — pending sign-up"}</p>
                </div>
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
            ))
          )}
        </ul>
        <p className="text-xs text-muted-foreground">People see a shared note under Notes → Shared. Changes are saved to the same note; edits made at the same time are merged last-write-wins for now.</p>
      </DialogContent>
    </Dialog>
  );
}
