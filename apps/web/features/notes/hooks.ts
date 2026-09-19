"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { foldersApi, notesApi, searchApi, tagsApi } from "@/features/notes/api";
import type { Note, NoteCreateInput, NoteListParams, NoteSummary, NoteUpdateInput } from "@/lib/api/types";

export const noteKeys = {
  all: ["notes"] as const,
  list: (params: NoteListParams) => ["notes", "list", params] as const,
  detail: (id: string) => ["notes", "detail", id] as const,
  folders: ["folders"] as const,
  tags: ["tags"] as const,
  search: (q: string) => ["search", q] as const,
};

export function useNotesList(params: NoteListParams) {
  return useInfiniteQuery({
    queryKey: noteKeys.list(params),
    queryFn: ({ pageParam }) => notesApi.list({ ...params, cursor: pageParam || undefined }),
    initialPageParam: "",
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });
}

export function useNote(id: string | null) {
  return useQuery({
    queryKey: noteKeys.detail(id ?? ""),
    queryFn: () => notesApi.get(id as string),
    enabled: Boolean(id),
    staleTime: 10_000,
  });
}

/** Apply a saved note to every cached list/detail without a refetch storm. */
function patchCaches(queryClient: ReturnType<typeof useQueryClient>, note: Note | NoteSummary) {
  queryClient.setQueryData<Note>(noteKeys.detail(note.id), (old) =>
    old ? { ...old, ...note } : ("content_json" in note ? (note as Note) : old),
  );
  queryClient.invalidateQueries({ queryKey: ["notes", "list"] });
}

export function useCreateNote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: NoteCreateInput = {}) => notesApi.create(input),
    onSuccess: (note) => {
      queryClient.setQueryData(noteKeys.detail(note.id), note);
      queryClient.invalidateQueries({ queryKey: ["notes", "list"] });
      queryClient.invalidateQueries({ queryKey: noteKeys.folders });
    },
  });
}

export function useUpdateNote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: NoteUpdateInput }) => notesApi.update(id, input),
    onSuccess: (note) => {
      patchCaches(queryClient, note);
      if (note.tags) queryClient.invalidateQueries({ queryKey: noteKeys.tags });
      queryClient.invalidateQueries({ queryKey: noteKeys.folders });
    },
  });
}

export function useNoteActions() {
  const queryClient = useQueryClient();
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["notes", "list"] });
    queryClient.invalidateQueries({ queryKey: noteKeys.folders });
    queryClient.invalidateQueries({ queryKey: noteKeys.tags });
  };
  const trash = useMutation({
    mutationFn: notesApi.trash,
    onSuccess: (note) => {
      patchCaches(queryClient, note);
      refresh();
    },
  });
  const restore = useMutation({
    mutationFn: notesApi.restore,
    onSuccess: (note) => {
      patchCaches(queryClient, note);
      refresh();
    },
  });
  const purge = useMutation({
    mutationFn: notesApi.purge,
    onSuccess: (_, id) => {
      queryClient.removeQueries({ queryKey: noteKeys.detail(id) });
      refresh();
    },
  });
  const duplicate = useMutation({
    mutationFn: notesApi.duplicate,
    onSuccess: (note) => {
      queryClient.setQueryData(noteKeys.detail(note.id), note);
      refresh();
    },
  });
  return { trash, restore, purge, duplicate };
}

export function useFolders() {
  return useQuery({ queryKey: noteKeys.folders, queryFn: foldersApi.list, staleTime: 60_000 });
}

export function useFolderMutations() {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: noteKeys.folders });
    queryClient.invalidateQueries({ queryKey: ["notes"] });
  };
  return {
    create: useMutation({ mutationFn: foldersApi.create, onSuccess: invalidate }),
    update: useMutation({
      mutationFn: ({ id, ...input }: { id: string; name?: string; parent_id?: string | null }) =>
        foldersApi.update(id, input),
      onSuccess: invalidate,
    }),
    remove: useMutation({ mutationFn: foldersApi.remove, onSuccess: invalidate }),
  };
}

export function useTags() {
  return useQuery({ queryKey: noteKeys.tags, queryFn: tagsApi.list, staleTime: 60_000 });
}

export function useTagMutations() {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: noteKeys.tags });
    queryClient.invalidateQueries({ queryKey: ["notes"] });
  };
  return {
    create: useMutation({ mutationFn: tagsApi.create, onSuccess: invalidate }),
    update: useMutation({
      mutationFn: ({ id, ...input }: { id: string; name?: string; color?: string | null }) =>
        tagsApi.update(id, input),
      onSuccess: invalidate,
    }),
    remove: useMutation({ mutationFn: tagsApi.remove, onSuccess: invalidate }),
  };
}

export function useSearch(q: string) {
  const trimmed = q.trim();
  return useQuery({
    queryKey: noteKeys.search(trimmed),
    queryFn: () => searchApi.search(trimmed),
    enabled: trimmed.length > 0,
    staleTime: 15_000,
    placeholderData: (prev) => prev,
  });
}
