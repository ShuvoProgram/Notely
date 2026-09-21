import { expect, test, type Page } from "@playwright/test";

/**
 * These tests drive the real agent pipeline (LangGraph + Postgres checkpoints + approvals) with
 * the scripted model provider (AI_PROVIDER=fake) so they are deterministic and need no model key.
 */

const password = "a perfectly fine passphrase";

async function signup(page: Page) {
  const email = `e2e-ai-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("Name").fill("AI Tester");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

type Reply = { content?: string; tool_calls?: { name: string; args: Record<string, unknown>; id: string }[] };

async function script(page: Page, replies: Reply[]) {
  const res = await page.request.post("/api/v1/ai/_dev/script", { data: { replies }, headers: { Origin: "http://localhost:3000" } });
  expect(res.ok(), await res.text()).toBeTruthy();
}

async function createNote(page: Page, title: string, body: string) {
  const res = await page.request.post("/api/v1/notes", {
    data: { title, content_json: { type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text: body }] }] } },
    headers: { Origin: "http://localhost:3000" },
  });
  expect(res.ok()).toBeTruthy();
  return ((await res.json()) as { data: { id: string } }).data.id;
}

test("assistant searches notes automatically and cites sources", async ({ page }) => {
  await signup(page);
  await createNote(page, "Launch plan", "Ship the pricing page by Friday.");
  await script(page, [
    { tool_calls: [{ name: "search_notes", args: { query: "pricing" }, id: "c1" }] },
    { content: "Your **Launch plan** says to ship the pricing page by Friday." },
  ]);
  await page.goto("/app/ai");
  await page.getByLabel("Ask anything").fill("What does my launch plan say?");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByText("ship the pricing page by Friday")).toBeVisible();
  await expect(page.getByText("Based on 1 source")).toBeVisible();
  await expect(page.getByRole("link", { name: "Launch plan" })).toBeVisible();
  await expect(page).toHaveURL(/thread=/);
  // No approval card for read-only tools.
  await expect(page.getByText("Ready to execute")).toHaveCount(0);
});

test("write actions pause for review; approving one of two executes only that one", async ({ page }) => {
  await signup(page);
  await script(page, [
    {
      tool_calls: [
        { name: "create_task", args: { title: "Finalize pricing", priority: "high" }, id: "c1" },
        { name: "create_task", args: { title: "Email the team" }, id: "c2" },
      ],
    },
    { content: "Created the approved task." },
  ]);
  await page.goto("/app/ai");
  await page.getByLabel("Ask anything").fill("Turn my launch plan into tasks");
  await page.getByLabel("Ask anything").press("Enter");

  const card = page.getByRole("region", { name: "Ready to execute" });
  await expect(card).toBeVisible();
  await expect(card.getByText("Notely wants to make 2 changes")).toBeVisible();
  await expect(card.getByText("Create task “Finalize pricing”")).toBeVisible();
  await expect(card.getByText("Create task “Email the team”")).toBeVisible();

  // Untick the second proposal, approve the rest.
  await card.getByLabel(/Email the team/).uncheck();
  await script(page, [{ content: "Created the approved task." }]);
  await card.getByRole("button", { name: "Approve 1 of 2" }).click();

  await expect(page.getByText("Created the approved task.")).toBeVisible();
  await expect(page.getByRole("region", { name: "Ready to execute" })).toHaveCount(0);

  await page.goto("/app/tasks");
  await expect(page.getByText("Finalize pricing")).toBeVisible();
  await expect(page.getByText("Email the team")).toHaveCount(0);
  await expect(page.getByText("High", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("AI", { exact: true }).first()).toBeAttached(); // the AI badge is hidden on phones
});

test("note actions preview a suggestion and only change the note on Insert", async ({ page }) => {
  await signup(page);
  const noteId = await createNote(page, "Meeting", "We agreed to ship on Friday. Bob owns QA.");
  await script(page, [{ content: "Ship Friday; Bob owns QA." }]);
  await page.goto(`/app/notes/${noteId}`);

  await page.getByRole("button", { name: "Ask AI" }).click();
  await page.getByRole("menuitem", { name: "Summarize" }).click();
  const panel = page.getByRole("complementary", { name: "AI suggestion" });
  await expect(panel.getByText("Ship Friday; Bob owns QA.")).toBeVisible();
  // Preview only: the body is untouched until the user acts.
  const body = page.getByRole("textbox", { name: "Note body" });
  await expect(body).not.toContainText("Ship Friday;");

  await panel.getByRole("button", { name: "Insert" }).click();
  await expect(body).toContainText("Ship Friday; Bob owns QA.");
  await expect(body).toContainText("We agreed to ship on Friday.");
  await expect(page.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible({ timeout: 10_000 });
});

test("extract tasks offers a checklist and adds the chosen ones", async ({ page }) => {
  await signup(page);
  const noteId = await createNote(page, "Todo", "Call Sam tomorrow. Send the invoice.");
  await script(page, [{ content: '[{"title":"Call Sam","due_date":null,"priority":"medium"},{"title":"Send the invoice","due_date":"2026-10-01","priority":"none"}]' }]);
  await page.goto(`/app/notes/${noteId}`);
  await page.getByRole("button", { name: "Ask AI" }).click();
  await page.getByRole("menuitem", { name: "Extract action items" }).click();
  const panel = page.getByRole("complementary", { name: "AI suggestion" });
  await expect(panel.getByText("Call Sam")).toBeVisible();
  await panel.getByLabel(/Send the invoice/).uncheck();
  await panel.getByRole("button", { name: "Add 1 to tasks" }).click();
  await expect(page.getByText("Added 1 task")).toBeVisible();

  await page.goto("/app/tasks");
  await expect(page.getByText("Call Sam")).toBeVisible();
  await expect(page.getByText("Send the invoice")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Open source note" })).toBeVisible();
});

test("cross-app request: plan is shown and ticked off, writes are verified after approval", async ({ page }) => {
  await signup(page);
  await createNote(page, "Launch plan", "Finalize the pricing page by Friday.");
  await script(page, [
    {
      tool_calls: [
        {
          name: "plan_steps",
          args: {
            goal: "Prepare the launch follow-up",
            steps: [
              { title: "Find launch material", kind: "read", tools: ["search_everything"] },
              { title: "Propose follow-up tasks", kind: "propose", tools: ["create_task"] },
              { title: "Confirm the tasks exist", kind: "verify", tools: [] },
              { title: "Summarise for you", kind: "answer", tools: [] },
            ],
          },
          id: "p1",
        },
        { name: "search_everything", args: { query: "pricing" }, id: "c1" },
      ],
    },
    { tool_calls: [{ name: "create_task", args: { title: "Finalize pricing" }, id: "c2" }] },
  ]);
  await page.goto("/app/ai");
  await page.getByLabel("Ask anything").fill("Prepare the follow-up from my launch plan");
  await page.getByLabel("Ask anything").press("Enter");

  const plan = page.getByRole("region", { name: "Plan" });
  await expect(plan).toBeVisible();
  await expect(plan.getByText("Prepare the launch follow-up")).toBeVisible();
  const card = page.getByRole("region", { name: "Ready to execute" });
  await expect(card).toBeVisible();
  await expect(plan.getByText("needs your approval")).toBeVisible();
  await expect(plan.locator('li[data-status="done"]')).toHaveCount(1); // the read step

  await script(page, [{ content: "Created the task and verified it exists." }]);
  await card.getByRole("button", { name: /Approve/ }).click();
  await expect(page.getByText("Created the task and verified it exists.")).toBeVisible();
  await expect(page.getByText("Verified", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Plan" }).locator('li[data-status="done"]')).toHaveCount(4);
  await expect(page.getByLabel("Sources")).toContainText("Based on 1 source");
  await expect(page.getByLabel("Sources").getByRole("link", { name: "Launch plan" })).toBeVisible();

  // The read-back is part of the audit trail, not hidden.
  await page.goto("/app/settings/activity");
  await expect(page.getByText("Checked: create_task")).toBeVisible();
  await expect(page.getByText("verified", { exact: true })).toBeVisible();
});

test("AI settings: bring your own model is saved encrypted, tested for real, and switched off again", async ({ page }) => {
  await signup(page);
  await page.goto("/app/settings/ai");
  await expect(page.getByText(/Requests go through the Notely model gateway/)).toBeVisible();

  await page.getByRole("button", { name: "Provider" }).click();
  await page.getByRole("menuitemradio", { name: "OpenAI-compatible endpoint" }).click();
  await expect(page.getByLabel("Base URL")).toHaveValue("http://localhost:11434/v1");
  await page.getByLabel("Base URL").fill("http://127.0.0.1:1/v1"); // nothing listens here
  await page.getByRole("textbox", { name: "Model name" }).fill("llama3.1");
  await page.getByLabel("API key").fill("sk-local-test-key-9876");
  await page.getByRole("button", { name: "Save model" }).click();
  await expect(page.getByText("In use")).toBeVisible();
  await expect(page.getByText(/key …9876/)).toBeVisible();
  await expect(page.getByText(/Requests go to your own openai_compatible model \(llama3\.1\)/)).toBeVisible();
  // The key never comes back: the field is empty and only the hint is shown.
  await expect(page.getByLabel("API key")).toHaveValue("");
  await expect(page.getByLabel("API key")).toHaveAttribute("placeholder", /Stored \(…9876\)/);

  // A real test against a dead endpoint fails with a categorised message, not a stack trace.
  await page.getByRole("button", { name: "Test" }).click();
  await expect(page.getByRole("status")).toContainText(/Failed: Could not reach the provider/, { timeout: 30_000 });
  await expect(page.getByText("Last test failed")).toBeVisible();

  await page.getByRole("button", { name: "Remove key" }).click();
  await expect(page.getByText(/Requests go through the Notely model gateway/)).toBeVisible();
});
