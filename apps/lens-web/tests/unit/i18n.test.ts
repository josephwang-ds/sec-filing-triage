import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/**
 * The bilingual audit, as a test.
 *
 * Two checks: the catalogues carry the same keys, and every literal key a
 * component asks for exists in both. The failure this prevents is the one the
 * Python page had -- a Chinese page with English strings in it, discovered by
 * a reader rather than by the build.
 */
const root = path.join(import.meta.dirname, "..", "..");
const en = JSON.parse(fs.readFileSync(path.join(root, "messages", "en.json"), "utf8"));
const zh = JSON.parse(fs.readFileSync(path.join(root, "messages", "zh.json"), "utf8"));

function flatten(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null) return [prefix];
  return Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
    flatten(child, prefix ? `${prefix}.${key}` : key),
  );
}

function sourceFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    return /\.tsx?$/.test(entry.name) ? [full] : [];
  });
}

const enKeys = new Set(flatten(en));
const zhKeys = new Set(flatten(zh));

describe("message catalogues", () => {
  it("carry the same keys in both languages", () => {
    expect([...enKeys].filter((key) => !zhKeys.has(key))).toEqual([]);
    expect([...zhKeys].filter((key) => !enKeys.has(key))).toEqual([]);
  });

  it("have no empty strings standing in for a translation", () => {
    const empty = (table: unknown, prefix = ""): string[] => {
      if (typeof table === "string") return table.trim() ? [] : [prefix];
      if (typeof table !== "object" || table === null) return [];
      return Object.entries(table as Record<string, unknown>).flatMap(([key, child]) =>
        empty(child, prefix ? `${prefix}.${key}` : key),
      );
    };
    expect(empty(en)).toEqual([]);
    expect(empty(zh)).toEqual([]);
  });

  it("use the same interpolation placeholders in both languages", () => {
    const placeholders = (table: unknown, prefix = ""): Record<string, string[]> => {
      if (typeof table === "string") {
        return { [prefix]: [...table.matchAll(/\{(\w+)\}/g)].map((match) => match[1]!).sort() };
      }
      if (typeof table !== "object" || table === null) return {};
      return Object.assign(
        {},
        ...Object.entries(table as Record<string, unknown>).map(([key, child]) =>
          placeholders(child, prefix ? `${prefix}.${key}` : key),
        ),
      );
    };
    const left = placeholders(en);
    const right = placeholders(zh);
    const mismatched = Object.keys(left).filter(
      (key) => JSON.stringify(left[key]) !== JSON.stringify(right[key]),
    );
    // A Chinese string that drops {date} renders a sentence with a hole in it.
    expect(mismatched).toEqual([]);
  });
});

describe("keys the components actually ask for", () => {
  const files = sourceFiles(path.join(root, "src"));

  it("resolves every literal translation key in both languages", () => {
    const missing: string[] = [];
    for (const file of files) {
      const text = fs.readFileSync(file, "utf8");
      // The namespace this file translates in, from useTranslations("x") or
      // getTranslations("x") / getTranslations({namespace: "x"}).
      const namespaces = [
        ...text.matchAll(/(?:useTranslations|getTranslations)\(\s*"([\w.]+)"\s*\)/g),
        ...text.matchAll(/namespace:\s*"([\w.]+)"/g),
      ].map((match) => match[1]!);
      if (namespaces.length !== 1) continue;
      const namespace = namespaces[0]!;
      for (const match of text.matchAll(/\bt\(\s*"([\w.]+)"/g)) {
        const key = `${namespace}.${match[1]}`;
        if (!enKeys.has(key) || !zhKeys.has(key)) {
          missing.push(`${path.relative(root, file)}: ${key}`);
        }
      }
    }
    expect(missing).toEqual([]);
  });

  it("covers every value of the dynamic key families", () => {
    // These are built from engine values at runtime, so a literal scan cannot
    // see them. The engine's full value set is listed here instead.
    const families: Record<string, string[]> = {
      "events.view": [
        "loading",
        "events",
        "no_new_events",
        "not_covered",
        "unavailable",
        "stale",
        "partial",
        "initializing",
        "error",
      ],
      "signal.state": ["read_now", "monitor", "routine", "insufficient_history", "withheld"],
      "volatility.state": [
        "typical_for_this_issuer",
        "elevated",
        "slightly_elevated",
        "unusually_calm",
      ],
      "filings.changeKind": ["changed", "added", "removed", "date"],
      "performance.unavailable": [
        "missing_prices",
        "stale_prices",
        "insufficient_overlap",
        "invalid_values",
      ],
      "financials.reference.reason": [
        "no_company_growth",
        "missing_classification",
        "insufficient_sample",
      ],
      "news.scope": ["available", "empty", "stale", "not_configured"],
      "ask.error": [
        "ask_not_configured",
        "model_not_available",
        "ticker_not_available",
        "scope_not_available",
        "question_length",
        "question_scope",
        "origin_not_allowed",
        "rate_limited",
        "daily_budget_exhausted",
        "grounding_validation_failed",
        "invalid_json",
        "network",
        "unknown",
      ],
    };
    const missing: string[] = [];
    for (const [family, values] of Object.entries(families)) {
      for (const value of values) {
        const key = `${family}.${value}`;
        if (!enKeys.has(key) || !zhKeys.has(key)) missing.push(key);
      }
    }
    expect(missing).toEqual([]);
  });
});
