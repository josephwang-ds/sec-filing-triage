import "server-only";

import fs from "node:fs";
import path from "node:path";
import { companySnapshot, type CompanySnapshot } from "@/lib/contracts/snapshot";

/**
 * The read side of the engine contract.
 *
 * `scripts/prepare-data.mjs` stages snapshots into `.lens/` before the build;
 * this module parses them once and hands out typed, validated read models. A
 * snapshot that fails validation is a build failure, not a page that renders
 * half a company: the whole point of the contract is that the front end cannot
 * quietly disagree with the engine about what a field means.
 */

export type DataSource = "engine" | "fixtures";

export interface Manifest {
  source: DataSource;
  snapshot_dir: string;
  generated_at: string;
  tickers: string[];
  ask: { available: boolean; reason: string | null };
}

export interface CompanyListing {
  ticker: string;
  name: string;
  category: string | null;
  categoryZh: string | null;
  asOf: string;
  filings: number | null;
}

const stage = path.join(process.cwd(), ".lens");

function readJson(file: string): unknown {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

let manifestCache: Manifest | null = null;

export function manifest(): Manifest {
  if (manifestCache) return manifestCache;
  const file = path.join(stage, "manifest.json");
  if (!fs.existsSync(file)) {
    throw new Error(
      `${file} is missing. Run \`npm run prepare-data\` (it runs automatically for \`npm run dev\` and \`npm run build\`).`,
    );
  }
  manifestCache = readJson(file) as Manifest;
  return manifestCache;
}

const snapshotCache = new Map<string, CompanySnapshot>();

export function snapshotTickers(): string[] {
  return manifest().tickers;
}

export function getSnapshot(ticker: string): CompanySnapshot | null {
  const symbol = ticker.trim().toUpperCase();
  const cached = snapshotCache.get(symbol);
  if (cached) return cached;
  const file = path.join(stage, "snapshots", `${symbol.toLowerCase()}.json`);
  if (!fs.existsSync(file)) return null;
  const parsed = companySnapshot.safeParse(readJson(file));
  if (!parsed.success) {
    throw new Error(
      `${file} does not match the snapshot contract. The engine and this front end disagree ` +
        `about the read model, so the page is not rendered.\n${JSON.stringify(parsed.error.issues.slice(0, 8), null, 2)}`,
    );
  }
  snapshotCache.set(symbol, parsed.data);
  return parsed.data;
}

export function requireSnapshot(ticker: string): CompanySnapshot {
  const snapshot = getSnapshot(ticker);
  if (!snapshot) throw new Error(`no snapshot for ${ticker}`);
  return snapshot;
}

export function listCompanies(): CompanyListing[] {
  return snapshotTickers()
    .map((ticker) => getSnapshot(ticker))
    .filter((snapshot): snapshot is CompanySnapshot => snapshot !== null)
    .map((snapshot) => ({
      ticker: snapshot.ticker,
      name: snapshot.profile.display_name ?? snapshot.company_name,
      category: snapshot.profile.category ?? null,
      categoryZh: snapshot.profile.category_zh ?? null,
      asOf: snapshot.as_of,
      filings: snapshot.profile.coverage?.filings_in_snapshot ?? null,
    }))
    .sort((a, b) => a.ticker.localeCompare(b.ticker));
}

/**
 * Featured issuers for the home page.
 *
 * Declared by `LENS_FEATURED` when set, otherwise the first three available.
 * Never a ranking: the Python index page made the same choice and said so, and
 * three cards in a row look like a leaderboard unless the page states what they
 * are.
 */
export function featuredCompanies(limit = 3): CompanyListing[] {
  const requested = (process.env.LENS_FEATURED ?? "")
    .split(/[,\s]+/)
    .map((value) => value.trim().toUpperCase())
    .filter(Boolean);
  const available = listCompanies();
  if (requested.length) {
    const byTicker = new Map(available.map((company) => [company.ticker, company]));
    const picked = requested
      .map((ticker) => byTicker.get(ticker))
      .filter((company): company is CompanyListing => company !== undefined);
    if (picked.length) return picked.slice(0, limit);
  }
  return available.slice(0, limit);
}
