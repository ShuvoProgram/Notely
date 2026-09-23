import { api } from "@/lib/api/client";
import type {
  ChangePasswordInput,
  LoginInput,
  SignInProvider,
  SignupInput,
  UpdateProfileInput,
  User,
  UserSession,
} from "@/lib/api/types";

export const authApi = {
  me: () => api.get<User>("/users/me"),
  updateProfile: (input: UpdateProfileInput) => api.patch<User>("/users/me", input),
  uploadAvatar: (file: Blob) => {
    const form = new FormData();
    form.append("file", file, "avatar");
    return api.put<User>("/users/me/avatar", form);
  },
  removeAvatar: () => api.delete<User>("/users/me/avatar"),
  signup: (input: SignupInput) => api.post<User>("/auth/signup", input),
  login: (input: LoginInput) => api.post<User>("/auth/login", input),
  verifyTwoFactor: (code: string) => api.post<{ verified: boolean }>("/auth/2fa/verify", { code }),
  logout: () => api.post<{ logged_out: boolean }>("/auth/logout"),
  logoutAll: () => api.post<{ revoked: number }>("/auth/logout-all"),
  changePassword: (input: ChangePasswordInput) =>
    api.post<{ changed: boolean }>("/auth/change-password", input),
  sessions: () => api.get<UserSession[]>("/auth/sessions"),
  revokeSession: (id: string) => api.delete<{ revoked: boolean }>(`/auth/sessions/${id}`),
  providers: () => api.get<SignInProvider[]>("/auth/providers"),
};
