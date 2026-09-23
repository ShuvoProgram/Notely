import { expect, test, type Page } from "@playwright/test";

const password = "a perfectly fine passphrase";

async function signup(page: Page) {
  const email = `e2e-auto-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("Name").fill("Automation Tester");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

async function addAction(page: Page, search: string) {
  await page.getByRole("button", { name: "Add a step here" }).last().click();
  await page.getByRole("menuitem", { name: "Do something" }).click();
  const input = page.getByPlaceholder(/Search, e\.g\./);
  await expect(input).toBeVisible();
  await input.fill(search);
  await page.keyboard.press("Enter");
  await expect(input).toBeHidden();
}

test("build an automation by hand, test it safely, run it for real and switch it on", async ({ page }) => {
  test.setTimeout(120_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await signup(page);
  const note = (await (await page.request.post("/api/v1/notes", { data: { title: "Daily Email Summary" } })).json()).data;
  await page.request.post("/api/v1/tasks", { data: { title: "Call Sam about pricing" } });

  await page.goto("/app/automations");
  await expect(page.getByRole("heading", { name: "What can I automate?" })).toBeVisible();
  await page.getByRole("link", { name: "Build manually" }).first().click();
  await expect(page).toHaveURL(/\/app\/automations\/new$/);
  await page.getByLabel("Automation name").fill("Task digest");

  await addAction(page, "Find tasks");
  await addAction(page, "Summarize");
  // The new step already uses the previous step's data, shown in words rather than code.
  await expect(page.getByText("Find tasks › All tasks found").first()).toBeVisible();
  await addAction(page, "Add to a note");
  await expect(page.getByText(/Fill in “Note”/).first()).toBeVisible();
  await page.getByRole("combobox", { name: "Note" }).click();
  await page.getByRole("option", { name: "Daily Email Summary" }).click();
  await expect(page.getByText(/Fill in “Note”/)).toHaveCount(0);

  // Test: reads and AI run for real, the note change is only simulated.
  await page.getByRole("button", { name: "Test", exact: true }).click();
  await expect(page.getByText("Test finished")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/would add to a note/i).filter({ visible: true }).first()).toBeVisible();
  await expect(page).toHaveURL(/\/app\/automations\/[0-9a-f-]{36}$/);
  let saved = (await (await page.request.get(`/api/v1/notes/${note.id}`)).json()).data;
  expect(saved.plain_text).toBe("");

  // Run now: the worker executes it and the note really changes.
  await page.getByRole("button", { name: "Run now" }).click();
  await expect(page.getByText(/Updated note “Daily Email Summary”/).filter({ visible: true }).first()).toBeVisible({ timeout: 30_000 });
  saved = (await (await page.request.get(`/api/v1/notes/${note.id}`)).json()).data;
  expect(saved.plain_text.length).toBeGreaterThan(10);

  await page.getByRole("switch", { name: "Automation on" }).click();
  await expect(page.getByText("Every weekday · 9:00 AM · On")).toBeVisible();

  await page.getByRole("link", { name: "Automations" }).first().click();
  const card = page.getByRole("article", { name: "Task digest" });
  await expect(card.getByText(/Last run/)).toBeVisible();
  await expect(card.getByText("Every weekday · 9:00 AM")).toBeVisible();
  await expect(card.getByRole("switch", { name: "Task digest on" })).toBeChecked();
  expect(errors).toEqual([]);
});

test("a check that isn't met ends the run normally and changes nothing", async ({ page }) => {
  await signup(page);
  const created = await page.request.post("/api/v1/automations", {
    data: {
      name: "Only when busy",
      schedule_kind: "manual",
      schedule_config: {},
      timezone: "UTC",
      enabled: false,
      workflow: {
        version: 2,
        steps: [
          { kind: "action", id: "open_tasks", action: "notely.find_tasks", inputs: { status: "open" } },
          {
            kind: "filter",
            id: "busy",
            name: "Only continue if there are open tasks",
            condition: { match: "all", rules: [{ left: "{{steps.open_tasks.output.count}}", operator: "greater_than", right: 0 }] },
          },
          { kind: "action", id: "make", action: "notely.create_task", inputs: { title: "Should not exist" } },
        ],
      },
    },
  });
  expect(created.status()).toBe(201);
  const automation = (await created.json()).data;
  await page.goto(`/app/automations/${automation.id}`);
  await expect(page.getByText("Only continue if there are open tasks").filter({ visible: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Run now" }).click();
  await expect(page.getByText("Finished early")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/Stopped: Only continue if there are open tasks wasn't met/)).toBeVisible();
  const tasks = (await (await page.request.get("/api/v1/tasks")).json()).data;
  expect(tasks).toEqual([]);
});

test("Create with AI shows a real preview or an honest error — never a fake workflow", async ({ page }) => {
  await signup(page);
  await page.goto("/app/automations");
  await page.getByRole("button", { name: "Create with AI" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: /Every Friday at 4 PM/ }).click();
  await dialog.getByRole("button", { name: "Create automation" }).click();
  await expect(
    dialog.getByRole("heading", { name: "Here's what Notely will do" }).or(dialog.getByRole("alert")),
  ).toBeVisible({ timeout: 60_000 });
  if (await dialog.getByRole("alert").isVisible()) {
    // e.g. the local scripted gateway can't draft; nothing was created behind the user's back.
    const list = (await (await page.request.get("/api/v1/automations")).json()).data;
    expect(list).toEqual([]);
  }
});
