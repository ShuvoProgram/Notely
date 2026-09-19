import { api } from "@/lib/api/client";
import type { Connection, ConnectionTestResult, Provider, ProviderDetail } from "@/lib/api/types";

export const connectionsApi = {
  providers: () => api.get<Provider[]>("/integrations/providers"),
  provider: (id: string) => api.get<ProviderDetail>(`/integrations/providers/${id}`),
  connect: (providerId: string, input: { config: Record<string, unknown>; token?: string | null }) =>
    api.post<Connection>(`/integrations/providers/${providerId}/connect`, input),
  oauthStartUrl: (providerId: string, scopes: string[]) =>
    api.get<{ authorize_url: string }>(`/oauth/${providerId}/start-url${scopes.length ? `?scopes=${encodeURIComponent(scopes.join(","))}` : ""}`),
  test: (connectionId: string) => api.post<ConnectionTestResult>(`/integrations/connections/${connectionId}/test`),
  update: (connectionId: string, config: Record<string, unknown>) => api.patch<Connection>(`/integrations/connections/${connectionId}`, { config }),
  disconnect: (connectionId: string, purge: boolean) => api.delete<Connection>(`/integrations/connections/${connectionId}${purge ? "?purge=true" : ""}`),
};
