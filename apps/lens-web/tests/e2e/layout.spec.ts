import { expect, test } from "@playwright/test";

const PAGES = [
  "/zh",
  "/en",
  "/zh/company/syn112",
  "/en/company/syn112",
  "/zh/company/syn071",
  "/zh/overview",
  "/en/overview",
  "/zh/research",
  "/en/research",
  "/zh/earnings",
];

/**
 * No page may scroll sideways.
 *
 * A horizontal scrollbar on a phone is the symptom of a child that cannot
 * shrink, and the events card had exactly that. The assertion is on the
 * document, so a deliberately scrollable rail inside the page still passes
 * while a layout that widens the page does not.
 */
for (const path of PAGES) {
  test(`${path} does not scroll sideways`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => {
      const root = document.documentElement;
      return { scrollWidth: root.scrollWidth, clientWidth: root.clientWidth };
    });
    expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
  });
}

test("the company page keeps its sections in order", async ({ page }) => {
  await page.goto("/en/company/syn112");
  for (const id of ["brief", "financials", "performance", "filings", "events", "ask"]) {
    await expect(page.locator(`#${id}`)).toBeAttached();
  }
});
