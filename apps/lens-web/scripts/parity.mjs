#!/usr/bin/env node
/**
 * Compare what the Python page and the Next.js page actually show.
 *
 * `scripts/compare_lens_pages.py` renders the Python page for each snapshot and
 * writes the display literals the engine produces from it. This opens both
 * pages in a browser, reads the rendered text and links out of each, and
 * reports any literal that is not on both.
 *
 * In a browser because neither page can be compared as static HTML: the Python
 * page fills its history section in from an inline JSON block after load, so
 * its numbers are not in the file it serves. Comparing rendered DOM is the only
 * comparison that answers whether a reader sees the same number.
 *
 *   node apps/lens-web/scripts/parity.mjs --base-url http://127.0.0.1:4320
 */
import fs from "node:fs";
import path from "node:path";
import { chromium } from "@playwright/test";

const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  args.set(process.argv[index]?.replace(/^--/, ""), process.argv[index + 1]);
}
const baseUrl = args.get("base-url") ?? "http://127.0.0.1:4320";
const locale = args.get("locale") ?? "en";
const appRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const repoRoot = path.resolve(appRoot, "..", "..");
const expectedFile =
  args.get("expected") ?? path.join(repoRoot, "data", "build", "parity", "expected.json");

if (!fs.existsSync(expectedFile)) {
  console.error(
    `${expectedFile} is missing.\nRun: PYTHONPATH=src python scripts/compare_lens_pages.py`,
  );
  process.exit(1);
}

const cases = JSON.parse(fs.readFileSync(expectedFile, "utf8"));
const browser = await chromium.launch();
const report = [];
let failures = 0;

for (const testCase of cases) {
  const context = await browser.newContext();
  const page = await context.newPage();

  // Everything a reader can reach, including what is behind a disclosure
  // control: both pages collapse older filings, and innerText does not see
  // hidden content, so a closed <details> would read as a missing value on
  // both sides and the comparison would pass by agreeing about nothing.
  const readPage = () =>
    page.evaluate(() => {
      for (const details of document.querySelectorAll("details")) details.open = true;
      return {
        text: document.body.innerText.replace(/\s+/g, " "),
        links: [...document.querySelectorAll("a[href]")].map((a) => a.getAttribute("href")),
      };
    });

  // The Python page, from the file the renderer just wrote. Its scripts run,
  // which is what puts the history numbers on screen: the section is empty in
  // the served HTML and filled from an inline JSON block on load.
  await page.goto(`file://${testCase.old_page}`);
  await page
    .waitForFunction(
      () => (document.querySelector("#total-return")?.textContent ?? "").trim().length > 0,
      undefined,
      { timeout: 5_000 },
    )
    .catch(() => undefined);
  await page.waitForTimeout(400);
  const old = await readPage();

  // The Next.js page for the same issuer.
  const url = `${baseUrl}/${locale}/company/${testCase.ticker.toLowerCase()}`;
  const response = await page.goto(url, { waitUntil: "networkidle" });
  if (!response || !response.ok()) {
    console.error(`${testCase.ticker}: ${url} returned ${response?.status() ?? "no response"}`);
    failures += 1;
    await context.close();
    continue;
  }
  const fresh = await readPage();
  await context.close();

  const rows = testCase.literals.map((item) => ({
    check: item.name,
    literal: item.literal,
    python: old.text.includes(item.literal),
    nextjs: fresh.text.includes(item.literal),
  }));
  for (const link of testCase.links) {
    rows.push({
      check: `source link ${link.split("/").pop()}`,
      literal: link,
      python: old.links.includes(link),
      nextjs: fresh.links.includes(link),
    });
  }

  const agreed = rows.filter((row) => row.python && row.nextjs).length;
  const mismatched = rows.filter((row) => !(row.python && row.nextjs));
  failures += mismatched.length;
  console.log(
    `${testCase.ticker} (${testCase.period}): ${agreed}/${rows.length} values match between pages`,
  );
  for (const row of mismatched) {
    console.log(
      `  MISMATCH ${row.check}: ${row.literal} — python=${row.python} nextjs=${row.nextjs}`,
    );
  }
  report.push({ ticker: testCase.ticker, url, period: testCase.period, rows });
}

await browser.close();
const out = path.join(repoRoot, "data", "build", "parity", "parity.json");
fs.writeFileSync(out, `${JSON.stringify(report, null, 2)}\n`);
console.log(`\nparity report -> ${out}`);
process.exit(failures ? 1 : 0);
