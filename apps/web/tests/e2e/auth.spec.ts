import { expect, test } from "@playwright/test";

const password = "a perfectly fine passphrase";

test("signup → workspace → sign out → sign in", async ({ page }) => {
  const email = `e2e-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;

  await page.goto("/signup");
  await page.getByLabel("Name").fill("E2E Tester");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole("heading", { name: /good to see you, e2e/i })).toBeVisible();

  // The session cookie must be HttpOnly and never readable from JS.
  const cookies = await page.context().cookies();
  const session = cookies.find((c) => c.name === "notely_session");
  expect(session?.httpOnly).toBe(true);
  expect(await page.evaluate(() => document.cookie)).not.toContain("notely_session");

  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);

  // Protected routes redirect when signed out.
  await page.goto("/app/settings/security");
  await expect(page).toHaveURL(/\/login$/);

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("not the password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert").filter({ hasText: /incorrect email or password/i })).toBeVisible();

  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/app$/);
});

test("security page lists the current session", async ({ page }) => {
  const email = `e2e-${Date.now()}-${Math.random().toString(36).slice(2)}@example.com`;
  await page.goto("/signup");
  await page.getByLabel("Name").fill("Session Tester");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/app$/);

  await page.goto("/app/settings/security");
  await expect(page.getByText("This device")).toBeVisible();
});
