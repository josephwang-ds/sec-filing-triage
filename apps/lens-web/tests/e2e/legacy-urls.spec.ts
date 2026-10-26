import { expect, test } from "@playwright/test";

/**
 * The Python site published one flat `.html` per issuer. Those URLs are linked
 * from the README, the main site, and the evidence packet's own citations, so
 * none of them may 404.
 */
const REDIRECTS: [string, RegExp][] = [
  ["/index.html", /\/(zh|en)$/],
  ["/overview.html", /\/(zh|en)\/overview$/],
  ["/research.html", /\/(zh|en)\/research$/],
  ["/earnings.html", /\/(zh|en)\/earnings$/],
  ["/syn112.html", /\/(zh|en)\/company\/syn112$/],
  ["/syn071.html", /\/(zh|en)\/company\/syn071$/],
];

for (const [from, to] of REDIRECTS) {
  test(`${from} still resolves`, async ({ page }) => {
    const response = await page.goto(from);
    expect(response?.status()).toBe(200);
    expect(page.url()).toMatch(to);
  });
}

test("/report.html stays the report entry instead of redirecting to research", async ({ page }) => {
  const response = await page.goto("/report.html");
  expect(response?.status()).toBe(200);
  expect(page.url()).toMatch(/\/report\.html$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/report/i);
  await expect(page.getByRole("heading", { level: 1 })).not.toHaveText("How this is measured");
});

test("a citation's in-page anchor survives the redirect", async ({ page }) => {
  // Ask citations point at `/<ticker>.html#performance`, which has to land on
  // the same section of the new page.
  await page.goto("/syn112.html#performance");
  expect(page.url()).toMatch(/#performance$/);
  await expect(page.locator("#performance")).toBeVisible();
});

test("an unknown company gets the boundary page, not an invented one", async ({ page }) => {
  const response = await page.goto("/zh/company/zzzz");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("这家公司");
});
