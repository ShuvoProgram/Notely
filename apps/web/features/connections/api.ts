import { api } from "@/lib/api/client";
import type { Connection, ConnectionTestResult, Provider, ProviderDetail } from "@/lib/api/types";

export const connectionsApi = {
  providers: () => api.get<Provider[]>("/integrations/providers"),
  provider: (id: string) => api.get<ProviderDetail>(`/integrations/providers/${id}`),
  oauthStartUrl: (providerId: string, scopes: string[], options: { method?: string; serverUrl?: string } = {}) => {
    const params = new URLSearchParams();
    if (scopes.length) params.set("scopes", scopes.join(","));
    if (options.method) params.set("method", options.method);
    if (options.serverUrl) params.set("server_url", options.serverUrl);
    const qs = params.toString();
    return api.get<{ authorize_url: string }>(`/oauth/${providerId}/start-url${qs ? `?${qs}` : ""}`);
  },
  test: (connectionId: string) => api.post<ConnectionTestResult>(`/integrations/connections/${connectionId}/test`),
  update: (connectionId: string, config: Record<string, unknown>) => api.patch<Connection>(`/integrations/connections/${connectionId}`, { config }),
  disconnect: (connectionId: string, purge: boolean) => api.delete<Connection>(`/integrations/connections/${connectionId}${purge ? "?purge=true" : ""}`),
};
