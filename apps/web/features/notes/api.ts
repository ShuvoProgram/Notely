import { api, apiEnvelope } from "@/lib/api/client";
import type {
  Collaborator,
  CollaboratorRole,
  Invitation,
  InviteResult,
  NoteVersion,
  NoteVersionDetail,
  Folder,
  Note,
  NoteCreateInput,
  NoteListParams,
  NoteSummary,
  NoteUpdateInput,
  SearchResponse,
  Tag,
} from "@/lib/api/types";

export interface NotePage {
  notes: NoteSummary[];
  nextCursor: string | null;
}

function qs(params: object): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params as Record<string, string | number | undefined>)) {
    if (v !== undefined && v !== "") search.set(k, String(v));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export const notesApi = {
  list: async (params: NoteListParams): Promise<NotePage> => {
    const { data, meta } = await apiEnvelope<NoteSummary[], { next_cursor?: string | null }>(
      `/notes${qs(params)}`,
    );
    return { notes: data, nextCursor: meta.next_cursor ?? null };
  },
  get: (id: string) => api.get<Note>(`/notes/${id}`),
  create: (input: NoteCreateInput) => api.post<Note>("/notes", input),
  update: (id: string, input: NoteUpdateInput) => api.patch<Note>(`/notes/${id}`, input),
  trash: (id: string) => api.delete<NoteSummary>(`/notes/${id}`),
  restore: (id: string) => api.post<NoteSummary>(`/notes/${id}/restore`),
  purge: (id: string) => api.delete<{ deleted: boolean }>(`/notes/${id}/permanent`),
  duplicate: (id: string) => api.post<Note>(`/notes/${id}/duplicate`),
  versions: (id: string) => api.get<NoteVersion[]>(`/notes/${id}/versions`),
  version: (id: string, versionId: string) => api.get<NoteVersionDetail>(`/notes/${id}/versions/${versionId}`),
  restoreVersion: (id: string, versionId: string) => api.post<Note>(`/notes/${id}/versions/${versionId}/restore`),
  invite: (id: string, input: { email: string; role: CollaboratorRole; resend?: boolean }) =>
    api.post<InviteResult>(`/notes/${id}/collaborators`, input),
  invitation: (token: string) => api.get<Invitation>(`/invitations/${encodeURIComponent(token)}`),
  acceptInvitation: (token: string) => api.post<Note>(`/invitations/${encodeURIComponent(token)}/accept`, {}),
  trashMany: (ids: string[]) => api.post<{ moved: number }>("/notes/bulk/trash", { ids }),
  restoreMany: (ids: string[]) => api.post<{ restored: number }>("/notes/bulk/restore", { ids }),
  /** Delete forever. The server only purges notes that are already in the trash. */
  purgeMany: (ids: string[]) => api.post<{ deleted: number }>("/notes/bulk/purge", { ids }),
  /** Drop your access to notes others shared with you. */
  leaveMany: (ids: string[]) => api.post<{ left: number }>("/notes/bulk/leave", { ids }),
  updateCollaborator: (id: string, collaboratorId: string, role: CollaboratorRole) =>
    api.patch<Collaborator>(`/notes/${id}/collaborators/${collaboratorId}`, { role }),
  removeCollaborator: (id: string, collaboratorId: string) =>
    api.delete<{ removed: boolean }>(`/notes/${id}/collaborators/${collaboratorId}`),
};

export const foldersApi = {
  list: () => api.get<Folder[]>("/folders"),
  create: (input: { name: string; parent_id?: string | null }) => api.post<Folder>("/folders", input),
  update: (id: string, input: { name?: string; parent_id?: string | null; position?: number }) =>
    api.patch<Folder>(`/folders/${id}`, input),
  remove: (id: string) => api.delete<{ deleted: boolean }>(`/folders/${id}`),
};

export const tagsApi = {
  list: () => api.get<Tag[]>("/tags"),
  create: (input: { name: string; color?: string | null }) => api.post<Tag>("/tags", input),
  update: (id: string, input: { name?: string; color?: string | null }) => api.patch<Tag>(`/tags/${id}`, input),
  remove: (id: string) => api.delete<{ deleted: boolean }>(`/tags/${id}`),
};

export const searchApi = {
  search: (q: string, limit = 20) => api.get<SearchResponse>(`/search${qs({ q, limit })}`),
};
