import { expect, test } from "@playwright/test";

/**
 * The events card, state by state.
 *
 * Each case routes `/api/events` to a feed the refresh pipeline can actually
 * produce, so the card is checked against the contract rather than against
 * whatever the deployment happens to be serving. No request leaves the machine.
 */
function feed(overrides: Record<string, unknown> = {}) {
  return {
    schema_version: "company-lens.events-public.v1",
    ticker: "SYN112",
    status: "current",
    status_label: { en: "Checked", zh: "已检查" },
    storage: "blob",
    coverage_tier: "high_frequency",
    tier_label: { en: "High-frequency coverage", zh: "高频覆盖" },
    coverage_gaps: [],
    checked_at: "2025-01-02T12:00:00+00:00",
    checked_at_display: {
      utc: "2025-01-02 12:00 UTC",
      new_york: "2025-01-02 07:00 New York",
      shanghai: "2025-01-02 20:00 Shanghai",
    },
    manifest_version: "9f2c1d44",
    ai_enabled: true,
    events: [],
    upcoming: [],
    ...overrides,
  };
}

const EVENT = {
  id: "evt-1",
  title: "SYN112 reports fourth-quarter results",
  title_language: "en",
  publisher: "Fixture Newswire",
  source_url: "https://example.invalid/fixture/one",
  source_published_at: "2025-01-02T11:30:00+00:00",
  time_precision: "minute",
  significance: { en: "New headline since the previous check.", zh: "自上次检查后的新标题。" },
  when: { en: "2025-01-02 11:30 UTC", new_york: "2025-01-02 06:30", shanghai: "2025-01-02 19:30" },
};

async function serve(page: import("@playwright/test").Page, body: unknown, status = 200) {
  await page.route("**/api/events*", async (route) => {
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
}

test("a company outside the fetch set says so, and says what still works", async ({ page }) => {
  await serve(page, feed({ coverage_tier: "unsupported", status: "unavailable", events: [] }));
  await page.goto("/en/company/syn112");
  const events = page.locator("#events");
  await expect(events.getByText("No event coverage for this company")).toBeVisible();
  await expect(events.getByText(/Filings, financial results and price history/)).toBeVisible();
});

test("a failed source is not the same message as an uncovered company", async ({ page }) => {
  await serve(page, feed({ storage: "read_error", status: "unavailable" }));
  await page.goto("/en/company/syn112");
  await expect(page.locator("#events").getByText("Event feed currently unavailable")).toBeVisible();
});

test("a successful check with nothing new says that", async ({ page }) => {
  await serve(page, feed({ status: "no_new_events", events: [] }));
  await page.goto("/en/company/syn112");
  await expect(
    page.locator("#events").getByText("No new items since the last check"),
  ).toBeVisible();
});

test("no published version never renders as a version", async ({ page }) => {
  await serve(page, feed({ manifest_version: null, events: [EVENT] }));
  await page.goto("/zh/company/syn112");
  const events = page.locator("#events");
  await expect(events).not.toContainText("事件版本 none");
  await expect(events).not.toContainText("none");
  await events.getByText("技术细节").click();
  await expect(events.getByText("尚无已发布版本")).toBeVisible();
});

test("a real version appears only inside the technical fold", async ({ page }) => {
  await serve(page, feed({ events: [EVENT] }));
  await page.goto("/en/company/syn112");
  const events = page.locator("#events");
  // Not in the body of the card.
  await expect(events.getByText("9f2c1d44")).toBeHidden();
  await events.getByText("Technical details").click();
  await expect(events.getByText("9f2c1d44")).toBeVisible();
});

test("nothing confirmed ahead collapses to one line, not an empty column", async ({ page }) => {
  await serve(page, feed({ events: [EVENT], upcoming: [] }));
  await page.goto("/en/company/syn112");
  const events = page.locator("#events");
  await expect(events.getByText("No confirmed future dates.")).toBeVisible();
  // The second column is not rendered at all, so no tall blank region exists.
  await expect(events.getByRole("heading", { name: "Confirmed next" })).toHaveCount(0);
});

test("an expected date is never shown as a confirmed one", async ({ page }) => {
  await serve(
    page,
    feed({
      events: [EVENT],
      upcoming: [
        {
          id: "up-1",
          title: "Q1 results",
          confirmation: "expected",
          expected_window: "late April 2025",
        },
      ],
    }),
  );
  await page.goto("/en/company/syn112");
  const events = page.locator("#events");
  await expect(events.getByText("Expected")).toBeVisible();
  await expect(events.getByText("late April 2025")).toBeVisible();
  await expect(events.getByText("Confirmed", { exact: true })).toHaveCount(0);
});

test("a headline keeps the language it was published in", async ({ page }) => {
  await serve(page, feed({ events: [EVENT] }));
  await page.goto("/zh/company/syn112");
  const headline = page.locator('#events [lang="en"]').first();
  await expect(headline).toContainText("SYN112 reports fourth-quarter results");
});

test("a broken payload offers a retry rather than a blank card", async ({ page }) => {
  await page.route("**/api/events*", async (route) => {
    await route.fulfill({ status: 500, contentType: "text/plain", body: "upstream exploded" });
  });
  await page.goto("/en/company/syn112");
  await expect(page.locator("#events").getByText("Event feed could not be loaded")).toBeVisible();
  await expect(page.locator("#events").getByRole("button", { name: "Check again" })).toBeVisible();
});

test("the card does not widen the page with a long headline", async ({ page }) => {
  await serve(
    page,
    feed({
      events: [
        {
          ...EVENT,
          title:
            "SYN112 Incorporated announces a comprehensive restructuring of its global manufacturing footprint together with revised full-year guidance",
          publisher: "A Very Long Fixture Publisher Name For Overflow Testing Limited",
        },
      ],
    }),
  );
  await page.goto("/zh/company/syn112");
  await page.waitForLoadState("networkidle");
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
});
