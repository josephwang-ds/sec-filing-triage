import { expect, test } from "@playwright/test";

/**
 * Language is a property of the reader, not of the page they happen to be on.
 */
test("switching language stays on the same company", async ({ page }) => {
  await page.goto("/zh/company/syn112");
  await expect(page.locator("html")).toHaveAttribute("lang", "zh");
  await page.getByRole("button", { name: "EN" }).click();
  await expect(page).toHaveURL(/\/en\/company\/syn112$/);
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  // The ticker is still the subject of the page, not just the URL.
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Synthetic Issuer 112");
});

test("language survives navigation and a reload", async ({ page }) => {
  await page.goto("/zh");
  await page.getByRole("button", { name: "EN" }).click();
  await expect(page).toHaveURL(/\/en$/);

  await page.getByRole("link", { name: "How this is audited" }).first().click();
  await expect(page).toHaveURL(/\/en\/research$/);

  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");

  // A bare path now resolves to the language last chosen, from the cookie the
  // switcher wrote -- not back to the default.
  await page.goto("/");
  await expect(page).toHaveURL(/\/en$/);
});

test("the first server render already carries the right language", async ({ request }) => {
  const chinese = await request.get("/zh/company/syn112");
  const html = await chinese.text();
  expect(html).toContain('lang="zh"');
  // Server-rendered, not swapped in by a script after paint.
  expect(html).toContain("公司概览");

  const english = await request.get("/en/company/syn112");
  expect(await english.text()).toContain('lang="en"');
});

test("original disclosure text is marked as English on the Chinese page", async ({ page }) => {
  await page.goto("/zh/company/syn112");
  // Quoted filing text and headlines keep their own language attribute, so a
  // screen reader does not read English prose with Chinese pronunciation.
  const english = page.locator('#filings [lang="en"], #context [lang="en"]');
  expect(await english.count()).toBeGreaterThan(0);
});
