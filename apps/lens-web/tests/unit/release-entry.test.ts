import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
const app = path.resolve(import.meta.dirname, "../..");
const temporary: string[] = [];
const valid = { status: "available", extraction: "company_facts", metrics: [{ id: "revenue", value: 1 }], source_url: "https://www.sec.gov/Archives/edgar/data/1/report.htm", period_end: "2026-06-30", filed: "2026-08-01", form: "10-Q" };
afterEach(() => temporary.splice(0).forEach(dir => fs.rmSync(dir, { recursive: true, force: true })));
// Exercise the real package entry and script; stub only the expensive Next compiler.
function run(report: unknown, staged = false, command = "build", omit = false) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lens-release-"));
  temporary.push(root);
  fs.mkdirSync(path.join(root, "scripts"));
  fs.copyFileSync(path.join(app, "scripts/prepare-data.mjs"), path.join(root, "scripts/prepare-data.mjs"));
  fs.copyFileSync(path.join(app, "package.json"), path.join(root, "package.json"));
  fs.mkdirSync(path.join(root, "node_modules/.bin"), { recursive: true });
  fs.writeFileSync(path.join(root, "node_modules/.bin/next"), "#!/bin/sh\necho NEXT_REACHED\n", { mode: 0o755 });
  const snapshots = path.join(root, staged ? ".lens/snapshots" : "input");
  fs.mkdirSync(snapshots, { recursive: true });
  for (const ticker of ["AAPL", "JPM", "NVDA", "KO", "V"]) {
    if (omit && ticker === "AAPL") continue;
    fs.writeFileSync(path.join(snapshots, `${ticker.toLowerCase()}.json`), JSON.stringify({ ticker, profile: {}, performance: {}, benchmark: "SPY", financial_results: ticker === "AAPL" ? report : ["KO", "V"].includes(ticker) ? { status: "unavailable", metrics: [] } : valid }));
  }
  if (staged) fs.writeFileSync(path.join(root, ".lens/manifest.json"), JSON.stringify({ source: "engine", tickers: ["AAPL", "JPM", "NVDA", "KO", "V"] }));
  fs.cpSync(path.join(app, "fixtures"), path.join(root, "fixtures"), { recursive: true });
  return spawnSync("npm", ["run", command], { cwd: root, encoding: "utf8", env: { ...process.env, LENS_REQUIRE_ENGINE: "0", LENS_REQUIRE_FINANCIALS: "0", LENS_REQUIRED_TICKERS: "", LENS_USE_FIXTURES: "", LENS_USE_STAGED: staged ? "1" : "", LENS_SNAPSHOT_DIR: snapshots } });
}
describe.each([false, true])("release entry staged=%s", staged => {
  it.each([undefined, "unknown", "published_html_fallback"])("rejects extraction %s despite disabled environment checks", extraction => {
    const result = run({ ...valid, extraction }, staged);
    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain("extraction must be company_facts");
    expect(result.stdout).not.toContain("NEXT_REACHED");
  });
  it.each([null, { ...valid, status: "unavailable" }, { ...valid, metrics: [] }, { ...valid, source_url: "https://example.com" }, { ...valid, filed: null }])("rejects incomplete required report %j", report => {
    expect(run(report, staged).status).not.toBe(0);
  });
  it("rejects missing snapshot even when a manifest claims it exists", () => {
    expect(run(valid, staged, "build", true).status).not.toBe(0);
  });
  it("accepts company facts and ordinary-company absences", () => {
    const result = run(valid, staged);
    expect(result.status, result.stderr).toBe(0);
    expect(result.stdout).toContain("NEXT_REACHED");
  });
});
it("keeps fixtures an explicit test build", () => {
  expect(run(null, false, "build:fixtures").status).toBe(0);
});
it("keeps missing-financial parity outside publishing", () => {
  expect(run(null, false, "build:parity").status).toBe(0);
});
it("validates final CI artifacts through the default release entry", () => {
  const workflow = fs.readFileSync(path.resolve(app, "../../.github/workflows/lens-v2-real-parity.yml"), "utf8").split("  full-universe-build:")[1] ?? "";
  expect(workflow).toContain("npm run build\n");
  expect(workflow).not.toContain("npm run build:parity");
  expect(workflow.indexOf("npm run build\n")).toBeLessThan(workflow.indexOf("uses: actions/upload-artifact"));
});
