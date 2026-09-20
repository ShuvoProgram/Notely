import { expect, test, type Page } from "@playwright/test";

/**
 * Drives the integration framework end to end against a real MCP server over Streamable HTTP
 * (apps/api/scripts/demo_mcp_server.py --port 8765 — a public server, so connecting needs no
 * consent step) and the scripted model.
 */

const MCP_URL = process.env.E2E_MCP_URL ?? "http://127.0.0.1:8765/mcp";
const password = "a perfectly fine passphrase";

async function signup(page: Page) {
  const email = `e2e-conn-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("Name").fill("Conn Tester");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

async function script(page: Page, replies: unknown[]) {
  const res = await page.request.post("/api/v1/ai/_dev/script", { data: { replies }, headers: { Origin: "http://localhost:3000" } });
  expect(res.ok(), await res.text()).toBeTruthy();
}

async function startMcpConnect(page: Page, url: string) {
  await page.goto("/app/settings/connections/mcp_server");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("You're in control")).toBeVisible();
  await dialog.getByLabel("Server URL").fill(url);
  await dialog.getByRole("button", { name: "Continue with Notely" }).click();
}

async function connectMcp(page: Page) {
  // One click: Notely discovers the server needs no sign-in and connects straight away.
  await startMcpConnect(page, MCP_URL);
  await expect(page.getByText("Connected", { exact: true }).first()).toBeVisible({ timeout: 15_000 });
}

test("marketplace lists providers with status and links to details", async ({ page }) => {
  await signup(page);
  await page.goto("/app/settings/connections");
  const card = page.getByRole("link", { name: /MCP server/ });
  await expect(card).toBeVisible();
  await expect(card.getByText("Not connected")).toBeVisible();
  await card.click();
  await expect(page).toHaveURL(/\/app\/settings\/connections\/mcp_server$/);
  await expect(page.getByRole("heading", { name: "MCP server" })).toBeVisible();
});

test("connect an MCP server, test it, use its tools with approval, then disconnect", async ({ page }) => {
  await signup(page);
  await connectMcp(page);

  // Detail page shows account, discovered tools with risk labels, and a healthy test.
  await expect(page.getByText("Demo Docs")).toBeVisible();
  await expect(page.getByText(/Tools \(4\)/)).toBeVisible();
  const toolsCard = page.getByText(/Tools \(4\)/).locator("..").locator("..");
  await expect(toolsCard.getByText("delete_page")).toBeVisible();
  await page.getByRole("button", { name: "Test connection" }).click();
  await expect(page.getByText("Connection healthy")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("4 tool(s) available")).toBeVisible();

  // The marketplace now shows it under Connected.
  await page.goto("/app/settings/connections");
  await expect(page.getByRole("heading", { name: "Connected" })).toBeVisible();

  // The assistant can read via the server automatically...
  await script(page, [
    { tool_calls: [{ name: "mcp_demo_docs__search_docs", args: { query: "pricing" }, id: "c1" }] },
    { content: "The Pricing FAQ says annual plans get two months free." },
  ]);
  await page.goto("/app/ai");
  await page.getByLabel("Ask anything").fill("What do the docs say about pricing?");
  await page.getByLabel("Ask anything").press("Enter");
  await expect(page.getByText("two months free")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("search docs on Demo Docs")).toBeVisible();
  await expect(page.getByRole("region", { name: "Ready to execute" })).toHaveCount(0);

  // ...but writing to it pauses for review, and the card names the provider.
  await script(page, [
    { tool_calls: [{ name: "mcp_demo_docs__create_page", args: { title: "Release notes", body: "v1" }, id: "c2" }] },
    { content: "Created the page." },
  ]);
  await page.getByRole("button", { name: "New", exact: true }).or(page.getByRole("button", { name: "New conversation" })).first().click();
  await page.getByLabel("Ask anything").fill("Create a release notes page");
  await page.getByLabel("Ask anything").press("Enter");
  const card = page.getByRole("region", { name: "Ready to execute" });
  await expect(card).toBeVisible({ timeout: 15_000 });
  await expect(card.getByText("create page on Demo Docs")).toBeVisible();
  await script(page, [{ content: "Created the page." }]);
  await card.getByRole("button", { name: /Approve/ }).click();
  await expect(page.getByText("Created the page.")).toBeVisible({ timeout: 15_000 });

  // Activity log recorded both executions with the provider.
  await page.goto("/app/settings/activity");
  await expect(page.getByText("search docs on Demo Docs")).toBeVisible();
  await expect(page.getByText("create page on Demo Docs")).toBeVisible();

  // Two-step disconnect; local data deletion is a separate, explicit choice.
  await page.goto("/app/settings/connections/mcp_server");
  await page.getByRole("button", { name: "Disconnect" }).click();
  await expect(page.getByText(/Your existing MCP server data will remain/)).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Disconnect", exact: true }).click();
  await expect(page.getByText(/Remove locally stored MCP server data\?/)).toBeVisible();
  await page.getByLabel(/Delete indexed MCP server content/).check();
  await page.getByRole("button", { name: "Disconnect and delete data" }).click();
  await expect(page.getByText("Not connected").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Connect", exact: true })).toBeVisible();
});

test("an unreachable server yields a categorised error and an error status", async ({ page }) => {
  await signup(page);
  await startMcpConnect(page, "http://127.0.0.1:9/mcp"); // nothing listens here
  await expect(page.getByText(/temporarily unavailable/).first()).toBeVisible({ timeout: 15_000 });
  await page.keyboard.press("Escape");
  await expect(page.getByText("Connection error")).toBeVisible();
});

test("marketplace lists every provider; connecting is always the vendor's own consent screen", async ({ page }) => {
  await signup(page);
  await page.goto("/app/settings/connections");
  for (const name of ["Slack", "Notion", "Todoist", "Asana", "Jira", "Microsoft Teams", "Outlook", "Dropbox", "Gmail", "Google Calendar", "Google Drive", "OneDrive", "ClickUp", "Stripe", "PayPal", "MCP server"]) {
    await expect(page.getByRole("link", { name: new RegExp(`^${name}\\b`) })).toBeVisible();
  }
  for (const heading of ["Communication", "Notes & Knowledge", "Tasks", "Project management", "Email & Calendar", "Storage", "Payments", "Developer"]) {
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
  }
  // No vendor OAuth app is registered locally: apps without an official MCP server wait for one.
  await expect(page.getByRole("link", { name: /^Todoist\b/ }).getByText("Not available on this deployment")).toBeVisible();
  await page.getByRole("link", { name: /^Todoist\b/ }).click();
  await expect(page.getByText(/An administrator needs to register an OAuth app/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Connect", exact: true })).toHaveCount(0);
  await expect(page.getByText("Read tasks and projects")).toBeVisible(); // permissions are still explained

  // Vendors with an official MCP server connect with one click: consent card → vendor screen.
  await page.goto("/app/settings/connections/notion");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  const consent = page.getByRole("dialog");
  await expect(consent.getByText("You're in control")).toBeVisible();
  await expect(consent.getByText("Apps may introduce elevated risk")).toBeVisible();
  await expect(consent.getByText("Data shared with this app")).toBeVisible();
  await expect(consent.getByRole("button", { name: "Continue with Notely" })).toBeVisible();
  await expect(consent.getByRole("link", { name: /Continue to Notion/ })).toBeVisible();
  await expect(consent.locator("input")).toHaveCount(0); // nothing to type, nothing to paste
});
