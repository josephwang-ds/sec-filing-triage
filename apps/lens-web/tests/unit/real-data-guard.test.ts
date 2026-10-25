import { spawnSync } from "node:child_process";
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

  it("never silently accepts explicit fixtures under real-data verification", () => {
    const result = stageWith({
      LENS_USE_FIXTURES: "1",
      LENS_REQUIRE_ENGINE: "true",
    });
    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain("LENS_REQUIRE_ENGINE=1");
  });
});
