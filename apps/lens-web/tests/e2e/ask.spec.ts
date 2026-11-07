import { expect, test } from "@playwright/test";

/**
 * Ask, without ever calling a model.
 *
 * Every state here resolves before a provider request would be made, or is
 * served from a routed response. The suite must never spend money to pass.
 */
test("with no provider configured, Ask says so instead of offering a form", async ({ page }) => {
  await page.route("**/api/ask", async (route) => {
    if (route.request().method() !== "GET") return route.abort();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        schema_version: "company-lens.ask-models.v2",
        models: [],
        scopes: [],
        default_scope: "core",
        limits: { evidence_only: true, configured: false },
      }),
    });
  });
  await page.goto("/en/company/syn112");
  const ask = page.locator("#ask");
  await expect(ask.getByText("Ask is not configured on this deployment")).toBeVisible();
  await expect(ask.getByRole("button", { name: "Ask" })).toHaveCount(0);
});

const CONFIG = {
  schema_version: "company-lens.ask-models.v2",
  models: [{ id: "openai", provider: "GPT", model: "test-model" }],
  scopes: [
    { id: "core", label: "Core financials", label_zh: "核心财务", description: "Filings." },
  ],
  default_scope: "core",
  limits: { max_question_characters: 280, requests_per_hour: 8 },
};

async function withConfig(
  page: import("@playwright/test").Page,
  post: { status: number; body: unknown },
) {
  await page.route("**/api/ask", async (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(CONFIG),
      });
    }
    return route.fulfill({
      status: post.status,
      contentType: "application/json",
      body: JSON.stringify(post.body),
    });
  });
}

test("a refused question shows the refusal, not an answer", async ({ page }) => {
  await withConfig(page, {
    status: 422,
    body: {
      error: "question_scope",
      message: "Ask about the supplied company evidence, not what to buy.",
    },
  });
  await page.goto("/en/company/syn112");
  await page.locator("#ask textarea").fill("Should I buy this stock?");
  await page.locator("#ask").getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.locator("#ask").getByText(/not what to buy or a price forecast/)).toBeVisible();
  await expect(page.locator("#ask").getByText("No unvalidated answer was shown.")).toBeVisible();
});

test("a withheld answer is reported as withheld", async ({ page }) => {
  await withConfig(page, {
    status: 502,
    body: { error: "grounding_validation_failed" },
  });
  await page.goto("/en/company/syn112");
  await page.locator("#ask textarea").fill("What did the latest filing disclose?");
  await page.locator("#ask").getByRole("button", { name: "Ask", exact: true }).click();
  await expect(
    page.locator("#ask").getByText(/did not pass evidence validation/),
  ).toBeVisible();
});

test("the daily budget message is distinct from a rate limit", async ({ page }) => {
  await withConfig(page, { status: 429, body: { error: "daily_budget_exhausted" } });
  await page.goto("/en/company/syn112");
  await page.locator("#ask textarea").fill("What did the latest filing disclose?");
  await page.locator("#ask").getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.locator("#ask").getByText(/budget for today/)).toBeVisible();
});

test("an answer renders its claims with their citations", async ({ page }) => {
  await withConfig(page, {
    status: 200,
    body: {
      schema_version: "company-lens.grounded-answer.v1",
      answer: [
        {
          text: "The latest 8-K reports results of operations for the quarter.",
          citations: [
            {
              id: "filing:0001000112-24-004326",
              label: "8-K filed 2024-12-31",
              url: "https://example.invalid/filing",
            },
          ],
        },
      ],
      boundaries: [{ text: "This does not establish future return.", citations: [] }],
      meta: {
        provider: "openai",
        model: "test-model",
        evidence_scope: "core",
        evidence_scope_label: "Core financials",
        evidence_as_of: "2024-12-31",
        validator_status: "passed",
      },
    },
  });
  await page.goto("/en/company/syn112");
  await page.locator("#ask textarea").fill("What did the latest filing disclose?");
  await page.locator("#ask").getByRole("button", { name: "Ask", exact: true }).click();
  const ask = page.locator("#ask");
  await expect(ask.getByText(/results of operations for the quarter/)).toBeVisible();
  await expect(ask.getByRole("link", { name: /8-K filed 2024-12-31/ })).toBeVisible();
  await expect(ask.getByText("Citation and format check passed")).toBeVisible();
  await ask.getByText("What this answer cannot show").click();
  await expect(ask.getByText(/does not establish future return/)).toBeVisible();
});

test("the real endpoint refuses a question with no evidence bundle", async ({ request }) => {
  // No route interception: this is the deployment's own /api/ask. It must
  // never answer, and it must not pretend the question was malformed.
  const response = await request.post("/api/ask", {
    data: { ticker: "SYN112", provider: "openai", question: "What changed?", scope: "core" },
  });
  expect([400, 404, 503]).toContain(response.status());
  const body = await response.json();
  expect(body.error).toBeTruthy();
});
