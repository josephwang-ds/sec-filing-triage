import { expect, test } from "@playwright/test";

test("a withheld growth rate states the change and the reason", async ({ page }) => {
  await page.goto("/en/company/syn112");
  const financials = page.locator("#financials");
  await expect(financials.getByText(/Growth percentage withheld for a zero base or a loss/).first()).toBeVisible();
  await expect(financials.getByText("Current: 2024-10-01 — 2024-12-31 · USD").first()).toBeVisible();
});

test("a Chinese page names English source text", async ({ page }) => {
  await page.goto("/zh/company/syn112");
  await expect(page.locator("#financials").getByText("不显示增长百分比").first()).toBeVisible();
  await expect(page.locator("#context").getByText("英文标题原文").first()).toBeVisible();
});
