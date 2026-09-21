import { expect, type Locator, type Page } from "@playwright/test";
import { format } from "date-fns";

/** Pick a day `offsetDays` from today in the app's calendar popover opened by `trigger`. */
export async function pickDate(page: Page, trigger: Locator, offsetDays: number): Promise<Date> {
  const target = new Date();
  target.setHours(0, 0, 0, 0);
  target.setDate(target.getDate() + offsetDays);
  await trigger.click();
  const calendar = page.getByRole("dialog").filter({ has: page.getByRole("grid") }).last();
  await expect(calendar).toBeVisible();
  const monthDelta = (target.getFullYear() - new Date().getFullYear()) * 12 + (target.getMonth() - new Date().getMonth());
  for (let i = 0; i < Math.abs(monthDelta); i++) {
    await calendar.getByRole("button", { name: monthDelta > 0 ? "Go to the Next Month" : "Go to the Previous Month" }).click();
  }
  // Day buttons are labelled "Tuesday, September 22nd, 2026" (plus ", Today" / ", selected").
  await calendar.getByRole("button", { name: new RegExp(`^${format(target, "EEEE, MMMM do, yyyy")}`) }).click();
  return target;
}

/** Type a time into the app's time popover opened by `trigger`, e.g. "10:00 am". */
export async function pickTime(page: Page, trigger: Locator, text: string): Promise<void> {
  await trigger.click();
  const input = page.getByLabel("Type a time");
  await input.fill(text);
  await input.press("Enter");
  await expect(input).toBeHidden();
}
