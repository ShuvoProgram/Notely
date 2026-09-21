import { expect, test, type Page } from "@playwright/test";

const password = "a perfectly fine passphrase";

async function signup(page: Page) {
  const email = `e2e-palette-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("Name").fill("Palette Tester");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
}

// Regression: the command palette rendered cmdk's Input/List outside a Command root and crashed
// the whole app ("Cannot read properties of undefined (reading 'subscribe')") on the first click.
test("global search opens by click and shortcut, searches notes, navigates, and never throws", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await signup(page);
  await page.goto("/app/notes");
  await page.getByRole("button", { name: "Create your first note" }).click();
  await expect(page).toHaveURL(/\/app\/notes\/[0-9a-f-]{36}$/);
  const noteUrl = page.url();
  await page.getByLabel("Note title").fill("Quarterly roadmap");
  await expect(page.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible({ timeout: 10_000 });

  // Mouse: open, empty query shows actions + navigation, Escape closes.
  await page.getByRole("button", { name: "Open command palette" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Search and commands" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("option", { name: /New note/ })).toBeVisible();
  await expect(dialog.getByRole("option", { name: /Settings/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  // Keyboard: Ctrl/⌘+K, type, pick the note with the keyboard.
  await page.goto("/app/tasks");
  await page.keyboard.press("ControlOrMeta+k");
  await expect(dialog).toBeVisible();
  await page.keyboard.type("roadmap");
  const hit = dialog.getByRole("option", { name: /Quarterly roadmap/ });
  await expect(hit).toBeVisible();
  await hit.click();
  await expect(page).toHaveURL(noteUrl);
  await expect(page.getByLabel("Note title")).toHaveValue("Quarterly roadmap");

  // No results: a calm empty state, not a crash.
  await page.keyboard.press("ControlOrMeta+k");
  await page.keyboard.type("zzz-nothing-here-zzz");
  await expect(dialog.getByText("Nothing matches yet.")).toBeVisible();
  await page.keyboard.press("Escape");

  expect(errors).toEqual([]);
});
