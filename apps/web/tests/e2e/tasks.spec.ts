import { expect, test, type Page } from "@playwright/test";

import { pickDate, pickTime } from "./pickers";

const password = "a perfectly fine passphrase";

async function signup(page: Page) {
  const email = `e2e-tasks-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("Name").fill("Task Tester");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

test("tasks: quick add, edit with date/time/priority, sections, complete, notifications", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await signup(page);
  await page.goto("/app/tasks");

  // Quick add.
  await page.getByLabel("New task").fill("Write the launch email");
  await page.keyboard.press("Enter");
  const row = page.getByRole("listitem").filter({ hasText: "Write the launch email" });
  await expect(row).toBeVisible();
  await expect(page.getByRole("heading", { name: /No date/ })).toBeVisible();

  // Edit: due tomorrow at 10:00, high priority, details.
  await row.getByRole("button", { name: /^Write the launch email/ }).click();
  const dialog = page.getByRole("dialog", { name: "Edit task" });
  await pickDate(page, dialog.getByLabel("Due date"), 1);
  await pickTime(page, dialog.getByLabel("Time"), "10:00 am");
  await dialog.getByLabel("Priority").click();
  await page.getByRole("option", { name: "High" }).click();
  await dialog.getByLabel("Details").fill("Draft, review with marketing, send.");
  // Calendar isn't connected: the switch explains and stays off.
  await expect(dialog.getByText(/Connect Google Calendar/)).toBeVisible();
  await expect(dialog.getByRole("switch")).toBeDisabled();
  await dialog.getByRole("button", { name: "Save changes" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("heading", { name: /Tomorrow/ })).toBeVisible();
  await expect(row.getByText(/Tomorrow · 10:00/)).toBeVisible();
  await expect(row.getByText("High")).toBeVisible();

  // New task via the dialog, overdue.
  await page.getByRole("button", { name: "New task" }).first().click();
  const create = page.getByRole("dialog", { name: "New task" });
  await create.getByLabel("Title").fill("Yesterday's report");
  await pickDate(page, create.getByLabel("Due date"), -1);
  await create.getByRole("button", { name: "Add task" }).click();
  await expect(page.getByRole("heading", { name: /Overdue/ })).toBeVisible();

  // The bell picked up the overdue reminder (and due-soon for tomorrow's task).
  await page.getByRole("button", { name: /Notifications/ }).click();
  const inbox = page.getByRole("list", { name: "Notifications" });
  await expect(inbox.getByText(/Overdue: Yesterday's report/)).toBeVisible({ timeout: 10_000 });
  await expect(inbox.getByText(/Due soon: Write the launch email/)).toBeVisible();
  await page.getByRole("button", { name: "Mark all read" }).click();
  await expect(page.getByRole("button", { name: /Notifications, \d+ unread/ })).toHaveCount(0);
  await page.keyboard.press("Escape");

  // Complete → moves to Done; undo brings it back.
  await row.getByRole("checkbox").click();
  await expect(row).toBeHidden();
  await page.getByRole("tab", { name: "Done" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Write the launch email" })).toBeVisible();

  // Delete from the list.
  await page.getByRole("tab", { name: "Open" }).click();
  await page.getByRole("button", { name: "Delete task Yesterday's report" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Yesterday's report" })).toBeHidden();

  // Settings: notification switches, Connections tab lives under Settings, no Search page.
  await page.goto("/app/settings/notifications");
  const reminders = page.getByRole("switch", { name: "Task reminders" });
  await expect(reminders).toBeChecked();
  await reminders.click();
  await expect(reminders).not.toBeChecked();
  await page.goto("/app/settings/connections");
  await expect(page.getByRole("heading", { name: "Connections" })).toBeVisible();
  await page.goto("/app/search");
  await expect(page.getByText("Page not found")).toBeVisible();
  expect(errors).toEqual([]);
});

test("select several tasks and delete them together", async ({ page }) => {
  await signup(page);
  await page.goto("/app/tasks");
  for (const t of ["Alpha task", "Beta task", "Gamma task"]) {
    await page.getByLabel("New task").fill(t);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("listitem").filter({ hasText: t })).toBeVisible();
  }
  await page.getByRole("button", { name: "Select tasks" }).click();
  await page.getByRole("checkbox", { name: "Select Alpha task" }).click();
  await page.getByRole("checkbox", { name: "Select Beta task" }).click();
  await expect(page.getByText("2 selected")).toBeVisible();
  await page.getByRole("toolbar", { name: "Selection" }).getByRole("button", { name: "Delete" }).click();
  const confirm = page.getByRole("dialog", { name: "Delete 2 tasks?" });
  await confirm.getByRole("button", { name: "Delete" }).click();
  await expect(confirm).toBeHidden();
  await expect(page.getByRole("listitem").filter({ hasText: "Alpha task" })).toHaveCount(0);
  await expect(page.getByRole("listitem").filter({ hasText: "Gamma task" })).toBeVisible();
  await expect(page.getByRole("toolbar", { name: "Selection" })).toHaveCount(0);
});
