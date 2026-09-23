/**
 * Landing-page content. Everything here describes something the product actually does today; the
 * integration list mirrors the providers registered in the API (apps/api/app/integrations).
 * No invented customers, testimonials or metrics.
 */

export interface Integration {
  name: string;
  /** simpleicons.org slug (the same source the in-app marketplace uses), when it has the logo. */
  slug?: string;
  /** Brand colour for a monogram tile, for vendors the icon CDN no longer carries. */
  mono?: string;
}

export const INTEGRATION_GROUPS: { label: string; items: Integration[] }[] = [
  {
    label: "Email, calendar & meetings",
    items: [
      { name: "Gmail", slug: "gmail" },
      { name: "Google Calendar", slug: "googlecalendar" },
      { name: "Google Meet", slug: "googlemeet" },
      { name: "Outlook", mono: "#0F6CBD" },
      { name: "Zoom", slug: "zoom" },
    ],
  },
  {
    label: "Docs & files",
    items: [
      { name: "Google Docs", slug: "googledocs" },
      { name: "Google Sheets", slug: "googlesheets" },
      { name: "Google Drive", slug: "googledrive" },
      { name: "OneDrive", mono: "#0364B8" },
      { name: "Dropbox", slug: "dropbox" },
      { name: "Notion", slug: "notion" },
    ],
  },
  {
    label: "Teams & projects",
    items: [
      { name: "Slack", mono: "#4A154B" },
      { name: "Microsoft Teams", mono: "#5B5FC7" },
      { name: "Jira", slug: "jira" },
      { name: "Asana", slug: "asana" },
      { name: "ClickUp", slug: "clickup" },
      { name: "Todoist", slug: "todoist" },
    ],
  },
];

export const logoUrl = (slug: string) => `https://cdn.simpleicons.org/${slug}`;

export const STEPS = [
  {
    key: "capture",
    title: "Capture",
    body: "Write the way you think. Folders, tags and favourites keep every note one search away.",
  },
  {
    key: "ask",
    title: "Ask",
    body: "Ask about anything in your notes, tasks and connected apps. Answers come with their sources.",
  },
  {
    key: "approve",
    title: "Approve",
    body: "The assistant plans the steps and proposes each change. Nothing runs until you approve it.",
  },
  {
    key: "done",
    title: "Done",
    body: "Tasks land on your list with dates, sync to Google Calendar, and automations keep things moving.",
  },
] as const;

export type StepKey = (typeof STEPS)[number]["key"];
