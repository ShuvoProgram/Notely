"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";

import { authApi } from "@/features/auth/api";
import { ApiError } from "@/lib/api/client";
import type { User } from "@/lib/api/types";

export const authKeys = {
  me: ["auth", "me"] as const,
  sessions: ["auth", "sessions"] as const,
  providers: ["auth", "providers"] as const,
};

export function useCurrentUser(initialData?: User) {
  return useQuery({
    queryKey: authKeys.me,
    queryFn: authApi.me,
    initialData,
    staleTime: 60_000,
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 2,
  });
}

export function useSignInProviders() {
  return useQuery({ queryKey: authKeys.providers, queryFn: authApi.providers, staleTime: Infinity });
}

/** Where to go after sign-in: an in-app path from `?next=`, never an external URL. */
export function safeNext(value: string | null | undefined): string {
  if (value && /^\/(app|invite)(\/|$|\?)/.test(value) && !value.startsWith("//")) return value;
  return "/app";
}

function useAfterAuth() {
  const params = useSearchParams();
  return safeNext(params.get("next"));
}

export function useLogin() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const next = useAfterAuth();
  return useMutation({
    mutationFn: authApi.login,
    onSuccess: (user) => {
      queryClient.setQueryData(authKeys.me, user);
      router.push(next);
      router.refresh();
    },
  });
}

export function useSignup() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const next = useAfterAuth();
  return useMutation({
    mutationFn: authApi.signup,
    onSuccess: (user) => {
      queryClient.setQueryData(authKeys.me, user);
      router.push(next);
      router.refresh();
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  const router = useRouter();
  return useMutation({
    mutationFn: authApi.logout,
    onSettled: () => {
      queryClient.clear();
      router.push("/login");
      router.refresh();
    },
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: authApi.updateProfile,
    onSuccess: (user) => queryClient.setQueryData(authKeys.me, user),
  });
}

export function useChangePassword() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: authApi.changePassword,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: authKeys.sessions }),
  });
}

export function useSessions() {
  return useQuery({ queryKey: authKeys.sessions, queryFn: authApi.sessions });
}

export function useRevokeSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: authApi.revokeSession,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: authKeys.sessions }),
  });
}

export function useLogoutOthers() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: authApi.logoutAll,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: authKeys.sessions }),
  });
}
