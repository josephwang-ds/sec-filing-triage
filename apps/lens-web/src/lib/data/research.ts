import "server-only";

import fs from "node:fs";
import path from "node:path";

/**
 * The research evidence package, read rather than retold.
 *
 * Every number on the overview and research pages comes through here, out of
 * the same `evidence/real_run/` files the Python pages read and the same files
 * the test suite checks. Nothing is typed into a component: a published result
 * that can be edited in a React file is a published result that will eventually
 * disagree with the run that produced it, which is the exact failure the
 * generated Python pages were built to prevent.
 *
 * A missing file is an absence, not a zero. The pages state which sections the
 * evidence did not cover rather than rendering a blank number.
 */

const stage = path.join(process.cwd(), ".lens", "research");

function readJson<T>(name: string): T | null {
  const file = path.join(stage, name);
  if (!fs.existsSync(file)) return null;
  try {
    return JSON.parse(fs.readFileSync(file, "utf8")) as T;
  } catch {
    return null;
  }
}

/** Minimal CSV reader: the evidence exports are comma-separated with quoted fields. */
function readCsv(name: string): Record<string, string>[] {
  const file = path.join(stage, name);
  if (!fs.existsSync(file)) return [];
  const text = fs.readFileSync(file, "utf8").trim();
  if (!text) return [];
  const rows: string[][] = [];
  let field = "";
  let row: string[] = [];
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        field += char;
      }
      continue;
    }
    if (char === '"') quoted = true;
    else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (char !== "\r") {
      field += char;
    }
  }
  row.push(field);
  rows.push(row);
  const header = rows.shift();
  if (!header) return [];
  return rows
    .filter((line) => line.length === header.length)
    .map((line) => Object.fromEntries(header.map((key, index) => [key, line[index] ?? ""])));
}

export interface Metrics {
  n_events: number;
  base_rate: number;
  roc_auc: number;
  average_precision: number;
  average_precision_ci_low?: number;
  average_precision_ci_high?: number;
  roc_auc_ci_low?: number;
  roc_auc_ci_high?: number;
  sessions: number;
  bootstrap_draws?: number;
  filings_per_session_median?: number;
  filings_per_session_p90?: number;
  daily_precision_at_5: number;
  daily_random_precision_at_5: number;
  daily_lift_at_5?: number;
  daily_sessions_at_5?: number;
  daily_arrival_precision_at_5?: number;
  daily_item_202_precision_at_5?: number;
  daily_oracle_precision_at_5?: number;
  operational_sessions_at_5?: number;
}

export interface Manifest {
  schema_version?: string;
  exported_at?: string;
  pipeline_config?: Record<string, unknown>;
  uncertainty?: { method?: string; draws?: number; sessions?: number };
  inputs?: Record<string, { rows?: number; sha256?: string }>;
}

export interface LadderStage {
  stage: string;
  note: string;
  n_events: number | null;
  average_precision: number | null;
  roc_auc: number | null;
  daily_precision_at_5: number | null;
  daily_lift_at_5: number | null;
  impossible_share: number | null;
}

function toNumber(value: string | undefined): number | null {
  if (value === undefined || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export interface ResearchEvidence {
  available: boolean;
  metrics: Metrics | null;
  manifest: Manifest | null;
  ladder: LadderStage[];
  nlpAblation: Record<string, string>[];
  modelComparison: Record<string, string>[];
  modelPaired: Record<string, string>[];
  capacity: Record<string, string>[];
  tradability: Record<string, string>[];
  anchoring: Record<string, string>[];
  calibration: {
    shipped?: string;
    metrics?: Record<string, number | string>;
    methods?: Record<string, number | string>[];
  } | null;
  calibrationComparison: Record<string, string>[];
  volatilityForecasters: Record<string, string>[];
  volatilityRegimes: Record<string, string>[];
  volatilityPaired: Record<string, string>[];
  selfRelative: Record<string, unknown> | null;
  volatility: {
    shipped?: string;
    reference?: string;
    task?: { horizon?: number; filings?: number; scored?: number };
    gates?: Record<string, { calibrated?: boolean }>;
  } | null;
}

let cache: ResearchEvidence | null = null;

export function researchEvidence(): ResearchEvidence {
  if (cache) return cache;
  const metrics = readJson<Metrics>("metrics.json");
  cache = {
    available: metrics !== null,
    metrics,
    manifest: readJson<Manifest>("manifest.json"),
    ladder: readCsv("leakage_study.csv").map((row) => ({
      stage: row.stage ?? "",
      note: row.note ?? "",
      n_events: toNumber(row.n_events),
      average_precision: toNumber(row.average_precision),
      roc_auc: toNumber(row.roc_auc),
      daily_precision_at_5: toNumber(row.daily_precision_at_5),
      daily_lift_at_5: toNumber(row.daily_lift_at_5),
      impossible_share: toNumber(row.impossible_share),
    })),
    nlpAblation: readCsv("nlp_feature_ablation.csv"),
    modelComparison: readCsv("model_comparison.csv"),
    modelPaired: readCsv("model_comparison_paired.csv"),
    capacity: readCsv("capacity_profile.csv"),
    tradability: readCsv("reaction_capture.csv"),
    anchoring: readCsv("anchoring_study.csv"),
    calibration: readJson("calibration_metrics.json"),
    calibrationComparison: readCsv("calibration_comparison.csv"),
    volatilityForecasters: readCsv("volatility_forecasters.csv"),
    volatilityRegimes: readCsv("volatility_by_regime.csv"),
    volatilityPaired: readCsv("volatility_paired.csv"),
    selfRelative: readJson<Record<string, unknown>>("self_relative_metrics.json"),
    volatility: readJson("volatility_metrics.json"),
  };
  return cache;
}
