import { expect, test, type Page } from "@playwright/test";

const password = "a perfectly fine passphrase";

async function signup(page: Page) {
  const email = `e2e-notes-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("Name").fill("Notes Tester");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);
  return email;
}

test("create a note, autosave, reload, and find it via search", async ({ page }) => {
  await signup(page);
  await page.goto("/app/notes");
  await page.getByRole("button", { name: "Create your first note" }).click();
  await expect(page).toHaveURL(/\/app\/notes\/[0-9a-f-]{36}$/);

  const title = page.getByLabel("Note title");
  await title.fill("Product launch plan");
  await title.press("Enter");
  const body = page.getByRole("textbox", { name: "Note body" });
  await expect(body).toBeFocused();
  await body.pressSequentially("Ship the pricing page by Friday.");
  await body.press("Enter");
  await body.pressSequentially("- Email the team about the launching timeline");

  // Autosave lands within the debounce window and reports back.
  await expect(page.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/\d+ words/)).toContainText("13 words");

  // Reload: content came from the server, not the DOM.
  await page.reload();
  await expect(page.getByLabel("Note title")).toHaveValue("Product launch plan");
  await expect(page.getByRole("textbox", { name: "Note body" })).toContainText("Ship the pricing page by Friday.");
  await expect(page.getByRole("textbox", { name: "Note body" }).locator("ul li")).toHaveCount(1);

  // The list shows the note with an excerpt (on phones the list is its own screen).
  await page.goto("/app/notes");
  const list = page.getByRole("complementary", { name: "Notes list" });
  await expect(list.getByText("Product launch plan")).toBeVisible();
  await expect(list.getByText(/Ship the pricing page/)).toBeVisible();

  // Search uses stemmed full-text search: "launch" matches "launching" in the body.
  await page.goto("/app/search");
  await page.getByRole("textbox", { name: "Search" }).fill("launching pricing");
  const hit = page.getByRole("link", { name: /Product launch plan/ });
  await expect(hit).toBeVisible();
  await expect(hit.getByText("Notely")).toBeVisible();
  await hit.click();
  await expect(page.getByLabel("Note title")).toHaveValue("Product launch plan");
});

test("tags, folders, favorites, archive and trash", async ({ page, isMobile }) => {
  await signup(page);

  // Folder from the sidebar (inside the navigation sheet on phones).
  await page.goto("/app/notes");
  if (isMobile) await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: "New folder" }).first().click();
  await page.getByLabel("Name").fill("Projects");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("link", { name: /^Projects/ }).first()).toBeVisible();

  // Note inside the folder.
  await page.getByRole("link", { name: /^Projects/ }).first().click();
  await expect(page).toHaveURL(/folder=/);
  await page.getByRole("complementary", { name: "Notes list" }).getByRole("button", { name: "New note" }).click();
  await expect(page).toHaveURL(/\/app\/notes\/[0-9a-f-]{36}/);
  await page.getByLabel("Note title").fill("Roadmap");
  await expect(page.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Projects", { exact: true }).filter({ visible: true }).first()).toBeVisible();

  // Tag: create from the picker.
  await page.getByRole("button", { name: "Add tag" }).click();
  await page.getByLabel("Search or create tag").fill("work");
  await page.getByRole("button", { name: /Create “work”/ }).click();
  await expect(page.getByText("work", { exact: true }).filter({ visible: true }).first()).toBeVisible();
  await page.keyboard.press("Escape");

  // Favorite.
  await page.getByRole("button", { name: "Add to favorites" }).click();
  await expect(page.getByRole("button", { name: "Remove from favorites" })).toBeVisible();
  if (isMobile) await page.goto("/app/notes");
  await page.getByRole("tab", { name: "Favorites" }).click();
  await expect(page.getByRole("complementary", { name: "Notes list" }).getByText("Roadmap")).toBeVisible();

  // Archive via actions menu, then find it under Archived.
  if (isMobile) await page.getByRole("complementary", { name: "Notes list" }).getByText("Roadmap").click();
  await page.getByRole("button", { name: "Note actions" }).click();
  await page.getByRole("menuitem", { name: "Archive" }).click();
  if (isMobile) await page.goto("/app/notes");
  await page.getByRole("tab", { name: "Archived" }).click();
  await expect(page.getByRole("complementary", { name: "Notes list" }).getByText("Roadmap")).toBeVisible();

  // Trash, read-only banner, restore.
  if (isMobile) await page.getByRole("complementary", { name: "Notes list" }).getByText("Roadmap").click();
  await page.getByRole("button", { name: "Note actions" }).click();
  await page.getByRole("menuitem", { name: "Move to trash" }).click();
  await expect(page).toHaveURL(/\/app\/notes(\?.*)?$/);
  await page.getByRole("tab", { name: "Trash" }).click();
  await page.getByRole("complementary", { name: "Notes list" }).getByText("Roadmap").click();
  await expect(page.getByText(/This note is in the trash/)).toBeVisible();
  await expect(page.getByLabel("Note title")).toHaveAttribute("readonly", "");
  await page.getByRole("button", { name: "Restore" }).first().click();
  await expect(page.getByText(/This note is in the trash/)).toHaveCount(0);
});

test("unsaved draft survives a crash-like reload", async ({ page }) => {
  await signup(page);
  await page.goto("/app/notes");
  await page.getByRole("button", { name: "Create your first note" }).click();
  await expect(page).toHaveURL(/\/app\/notes\/[0-9a-f-]{36}$/);
  await page.getByLabel("Note title").fill("Draft title");
  await expect(page.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible({ timeout: 10_000 });

  // Block the save endpoint, type more, then reload before the request can succeed.
  await page.route("**/api/v1/notes/*", (route) => (route.request().method() === "PATCH" ? route.abort() : route.continue()));
  const body = page.getByRole("textbox", { name: "Note body" });
  await body.click();
  await body.pressSequentially("Only in the browser so far");
  await expect(page.getByRole("status").filter({ hasText: /Offline|Couldn't save/ })).toBeVisible({ timeout: 10_000 });
  await page.unroute("**/api/v1/notes/*");
  page.on("dialog", (d) => d.accept());
  await page.reload();

  await expect(page.getByText("Restored unsaved changes")).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Note body" })).toContainText("Only in the browser so far");
  await expect(page.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible({ timeout: 10_000 });
  await page.reload();
  await expect(page.getByRole("textbox", { name: "Note body" })).toContainText("Only in the browser so far");
});

test("typing, switching to Tasks and coming back keeps the text (client-side navigation)", async ({ page }) => {
  // Regression: after an autosave the note cache kept the pre-edit body, so returning to the
  // note via in-app navigation showed the old text — and the next save wrote it back.
  await signup(page);
  await page.goto("/app/notes");
  await page.getByRole("button", { name: "Create your first note" }).click();
  await expect(page).toHaveURL(/\/app\/notes\/[0-9a-f-]{36}$/);
  const noteUrl = page.url();

  await page.getByLabel("Note title").fill("Standup notes");
  const body = page.getByRole("textbox", { name: "Note body" });
  await body.click();
  await body.pressSequentially("First thought, saved by autosave.");
  await expect(page.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible({ timeout: 10_000 });

  // Keep typing and leave immediately, before the debounce fires (the unmount flush must save it).
  await body.press("Enter");
  await body.pressSequentially("Second thought, typed right before leaving.");
  await page.getByRole("link", { name: "Tasks" }).first().click();
  await expect(page).toHaveURL(/\/app\/tasks/);

  // Back to the same note through the app (no reload): everything typed is still there.
  await page.getByRole("link", { name: "Notes" }).first().click();
  await page.getByRole("complementary", { name: "Notes list" }).getByText("Standup notes").click();
  await expect(page).toHaveURL(noteUrl);
  const bodyAgain = page.getByRole("textbox", { name: "Note body" });
  await expect(bodyAgain).toContainText("First thought, saved by autosave.");
  await expect(bodyAgain).toContainText("Second thought, typed right before leaving.");
  await expect(page.getByLabel("Note title")).toHaveValue("Standup notes");

  // Editing again saves against the latest version — no conflict banner.
  await bodyAgain.click();
  await bodyAgain.press("Control+End");
  await bodyAgain.pressSequentially(" Third.");
  await expect(page.getByRole("status").filter({ hasText: /^Saved$/ })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/changed elsewhere|conflict/i)).toHaveCount(0);

  // And the server has all of it.
  await page.reload();
  await expect(page.getByRole("textbox", { name: "Note body" })).toContainText("Second thought, typed right before leaving. Third.");
});
