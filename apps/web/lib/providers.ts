/** Display names for every source/provider id the API can return (mirrors the backend registry). */
export const PROVIDER_LABELS: Record<string, string> = {
  notely: "Notely",
  slack: "Slack",
  notion: "Notion",
  todoist: "Todoist",
  asana: "Asana",
  jira: "Jira",
  microsoft_teams: "Teams",
  outlook: "Outlook",
  dropbox: "Dropbox",
  mcp_server: "MCP server",
};

export function providerLabel(id: string): string {
  return PROVIDER_LABELS[id] ?? id;
}
