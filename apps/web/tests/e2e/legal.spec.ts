import { expect, test } from "@playwright/test";

// Public legal pages: reachable signed-out by direct URL (and after refresh), linked from the
// landing footer and the sign-up form, with proper titles.
test("privacy policy and terms are public and linked", async ({ page }) => {
  await page.goto("/privacy-policy");
  await expect(page).toHaveURL(/\/privacy-policy$/);
  await expect(page).toHaveTitle(/Privacy Policy · Notely AI/);
  await expect(page.getByRole("heading", { level: 1, name: "Privacy Policy" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Google OAuth and Google user data/ })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "Privacy Policy" })).toBeVisible();

  await page.goto("/terms-and-conditions");
  await expect(page).toHaveTitle(/Terms & Conditions · Notely AI/);
  await expect(page.getByRole("heading", { level: 1, name: "Terms & Conditions" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Limitation of liability/ })).toBeVisible();

  // Footer on the landing page links to both. The landing page is long and animated; wait for it
  // to finish loading so the footer isn't scrolled to mid-hydration (the dev build hydrates slowly).
  await page.goto("/", { waitUntil: "networkidle" });
  const footer = page.getByRole("contentinfo");
  await footer.getByRole("link", { name: "Privacy Policy" }).click();
  await expect(page).toHaveURL(/\/privacy-policy$/);
  await page.goto("/", { waitUntil: "networkidle" });
  await footer.getByRole("link", { name: "Terms & Conditions" }).click();
  await expect(page).toHaveURL(/\/terms-and-conditions$/);

  // Sign-up form states the agreement and links to both.
  await page.goto("/signup");
  await expect(page.getByText(/By creating an account you agree to the/)).toBeVisible();
  await page.getByRole("form").getByRole("link", { name: "Terms & Conditions" }).click();
  await expect(page).toHaveURL(/\/terms-and-conditions$/);
});
