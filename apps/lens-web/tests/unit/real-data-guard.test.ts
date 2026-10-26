import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

const appRoot = path.resolve(import.meta.dirname, "..", "..");
const script = path.join(appRoot, "scripts", "prepare-data.mjs");

function stageWith(env: Record<string, string>) {
  return spawnSync(process.execPath, [script], {
    cwd: appRoot,
    encoding: "utf8",
    env: {
      ...process.env,
      LENS_USE_STAGED: "",
      LENS_USE_FIXTURES: "",
      LENS_REQUIRED_TICKERS: "",
      LENS_REQUIRE_ENGINE: "",
      ...env,
    },
  });
}

describe("real-data release guard", () => {
  it("fails closed when engine data is absent, even though fixtures exist", () => {
    const result = stageWith({
      LENS_REQUIRE_ENGINE: "1",
      LENS_SNAPSHOT_DIR: path.join(appRoot, "missing-engine-output-for-test"),
    });
    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain("LENS_REQUIRE_ENGINE=1");
    expect(result.stderr).toContain("Refusing synthetic fixtures");
  });

  it("refuses a required production ticker when only fixtures are available", () => {
    const result = stageWith({
      LENS_USE_FIXTURES: "1",
      LENS_REQUIRED_TICKERS: "AAPL,JPM,NVDA",
    });
    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain("AAPL, JPM, NVDA");
  });

  it("refuses synthetic files sitting in the engine directory", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "lens-syn-"));
    fs.writeFileSync(
      path.join(dir, "syn001.json"),
      JSON.stringify({ ticker: "SYN001", profile: {}, performance: {}, benchmark: "SPY" }),
    );
    const result = stageWith({ LENS_SNAPSHOT_DIR: dir });
    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain("refusing synthetic snapshots");
    expect(result.stderr).toContain("SYN001");
    expect(result.stderr).not.toContain("from engine");
  });

  it("fails a release build when a required issuer has no filed report", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "lens-nofin-"));
    fs.writeFileSync(
      path.join(dir, "aapl.json"),
      JSON.stringify({
        ticker: "AAPL",
        profile: {},
        performance: {},
        benchmark: "SPY",
        financial_results: { status: "unavailable", metrics: [] },
      }),
    );
    const result = stageWith({
      LENS_REQUIRE_ENGINE: "1",
      LENS_REQUIRE_FINANCIALS: "1",
      LENS_REQUIRED_TICKERS: "AAPL",
      LENS_SNAPSHOT_DIR: dir,
    });
    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain("no filed financial report");
    expect(result.stderr).toContain("AAPL");
  });

  it("never silently accepts explicit fixtures under real-data verification", () => {
    const result = stageWith({
      LENS_USE_FIXTURES: "1",
      LENS_REQUIRE_ENGINE: "true",
    });
    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain("LENS_REQUIRE_ENGINE=1");
  });
});
