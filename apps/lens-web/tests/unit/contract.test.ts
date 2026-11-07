import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { companySnapshot } from "@/lib/contracts/snapshot";

/**
 * The front end and the engine agree about the read model, or the build stops.
 *
 * This runs against the committed fixtures and, when a checkout has engine
 * output staged, against that too. A field the engine renames is caught here
 * rather than as a blank card on a company page.
 */
const fixtureDir = path.join(import.meta.dirname, "..", "..", "fixtures", "snapshots");
const stagedDir = path.join(import.meta.dirname, "..", "..", ".lens", "snapshots");

function snapshotFiles(dir: string): string[] {
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((name) => name.endsWith(".json"))
    .map((name) => path.join(dir, name));
}

const fixtures = snapshotFiles(fixtureDir);
const staged = snapshotFiles(stagedDir);

describe("snapshot contract", () => {
  it("has fixtures to check", () => {
    expect(fixtures.length).toBeGreaterThan(0);
  });

  it.each([...fixtures, ...staged])("%s matches the contract", (file) => {
    const parsed = companySnapshot.safeParse(JSON.parse(fs.readFileSync(file, "utf8")));
    if (!parsed.success) {
      throw new Error(
        `${path.basename(file)} does not match:\n${JSON.stringify(parsed.error.issues.slice(0, 5), null, 2)}`,
      );
    }
    expect(parsed.success).toBe(true);
  });

  it("keeps the populated fixture populated", () => {
    // SYN112 is the fixture every module renders against. If an optional
    // section quietly disappears from it, the module that reads it stops
    // being covered by any test at all.
    const file = path.join(fixtureDir, "syn112.json");
    const snapshot = companySnapshot.parse(JSON.parse(fs.readFileSync(file, "utf8")));
    expect(snapshot.financial_results?.status).toBe("available");
    expect(snapshot.financial_results?.metrics.length).toBeGreaterThan(0);
    expect(snapshot.fundamentals?.status).toBe("available");
    expect(snapshot.disclosure_signal).toBeTruthy();
    expect(snapshot.volatility_forecast?.median).toBeTypeOf("number");
    expect(snapshot.headlines.length).toBeGreaterThan(0);
    expect(Object.keys(snapshot.period_options).length).toBeGreaterThan(1);
  });

  it("keeps the sparse fixture sparse", () => {
    // The other half of the pair: a company with prices and filings and
    // nothing else, which is what most covered companies actually look like.
    const file = path.join(fixtureDir, "syn071.json");
    const snapshot = companySnapshot.parse(JSON.parse(fs.readFileSync(file, "utf8")));
    expect(snapshot.financial_results?.status).toBe("unavailable");
    expect(snapshot.fundamentals).toBeUndefined();
    expect(snapshot.disclosure_signal).toBeUndefined();
    expect(snapshot.volatility_forecast).toBeUndefined();
    expect(snapshot.headlines).toEqual([]);
    expect(snapshot.latest_filings.length).toBeGreaterThan(0);
  });

  it("records why an unavailable benchmark comparison is unavailable", () => {
    const file = path.join(fixtureDir, "syn112.json");
    const snapshot = companySnapshot.parse(JSON.parse(fs.readFileSync(file, "utf8")));
    for (const comparison of Object.values(snapshot.benchmark_comparisons)) {
      if (comparison.status === "available") continue;
      // A comparison that is missing must say why, or the selector has no
      // honest way to disable itself.
      expect(comparison.reason).toBeTruthy();
    }
  });
});
