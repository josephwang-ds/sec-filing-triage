"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import type {
  BenchmarkComparison,
  PeriodOption,
  Performance,
} from "@/lib/contracts/snapshot";
import { GrowthChart } from "./GrowthChart";
import { StatCard } from "@/components/ui/StatCard";
import { count, money, multiple, percent, signedPercent } from "@/lib/format";

interface Props {
  ticker: string;
  /** The default benchmark. Filing reactions and AI evidence stay on it. */
  benchmark: string;
  periods: Record<string, PeriodOption>;
  comparisons: Record<string, BenchmarkComparison>;
  defaultPeriod: string;
}

/**
 * Module C. Historical return and risk, over a selected period and against a
 * selected benchmark.
 *
 * Every switch changes the chart, the period range, the ending value, the
 * relative return and every risk figure in one render, because they are all
 * read out of the same record -- the failure this replaces was a chart that
 * moved while a label beside it did not.
 *
 * A benchmark the engine could not match is disabled with the reason it gave,
 * never silently re-labelled: QQQ numbers under a SPY series is the one error
 * here that a reader cannot detect. Only this section follows the selector;
 * the brief, the filing reactions and the Ask evidence stay on the snapshot's
 * default benchmark, and the note below says so.
 */
export function PerformanceSection({
  ticker,
  benchmark,
  periods,
  comparisons,
  defaultPeriod,
}: Props) {
  const t = useTranslations("performance");
  const periodLabels = Object.keys(periods);
  const [period, setPeriod] = useState(defaultPeriod);
  const [symbol, setSymbol] = useState(benchmark);

  const benchmarks = useMemo(
    () => [
      { symbol: benchmark, status: "available", reason: null as string | null },
      ...Object.values(comparisons).map((comparison) => ({
        symbol: comparison.symbol,
        status: comparison.status,
        reason: comparison.reason ?? null,
      })),
    ],
    [benchmark, comparisons],
  );

  const record = useMemo(() => {
    if (symbol === benchmark) {
      return { option: periods[period] ?? null, reason: null as string | null };
    }
    const comparison = comparisons[symbol];
    if (!comparison) return { option: null, reason: "missing_prices" };
    const option = comparison.periods[period];
    if (!option || option.status !== "available" || !option.performance) {
      return { option: null, reason: option?.reason ?? comparison.reason ?? "insufficient_overlap" };
    }
    return { option: option as PeriodOption, reason: null };
  }, [benchmark, comparisons, period, periods, symbol]);

  const option = record.option;
  const stats: Performance | null = option?.performance ?? null;
  const asset = stats?.asset ?? null;
  const market = stats?.benchmark ?? null;
  const coverage = option?.coverage ?? null;

  function pickBenchmark(next: string) {
    setSymbol(next);
  }

  return (
    <section
      id="performance"
      className="scroll-mt-24 rounded-panel border border-line bg-panel p-5 shadow-card md:p-8"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <p className="lens-eyebrow m-0 mb-2">{t("eyebrow")}</p>
          <h2 className="lens-serif m-0 text-2xl text-balance md:text-3xl">{t("title")}</h2>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap lg:justify-end">
          <div
            className="flex gap-1 rounded-lg bg-paper p-1"
            role="group"
            aria-label={t("periodGroup")}
          >
            {periodLabels.map((label) => (
              <button
                key={label}
                type="button"
                aria-pressed={label === period}
                onClick={() => setPeriod(label)}
                className={[
                  "rounded-md px-3 py-1.5 text-xs font-bold",
                  label === period ? "bg-panel text-accent shadow-card" : "text-muted hover:text-ink",
                ].join(" ")}
              >
                {label}
              </button>
            ))}
          </div>
          <div
            className="flex gap-1 rounded-lg bg-paper p-1"
            role="group"
            aria-label={t("benchmarkGroup")}
          >
            {benchmarks.map((entry) => {
              const disabled = entry.status !== "available";
              return (
                <button
                  key={entry.symbol}
                  type="button"
                  disabled={disabled}
                  aria-pressed={entry.symbol === symbol}
                  title={
                    disabled && entry.reason
                      ? t(`unavailable.${entry.reason}` as "unavailable.missing_prices", {
                          symbol: entry.symbol,
                        })
                      : undefined
                  }
                  onClick={() => pickBenchmark(entry.symbol)}
                  className={[
                    "rounded-md px-3 py-1.5 text-xs font-bold",
                    entry.symbol === symbol
                      ? "bg-panel text-accent shadow-card"
                      : "text-muted hover:text-ink",
                    disabled ? "cursor-not-allowed opacity-40" : "",
                  ].join(" ")}
                >
                  {entry.symbol}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <p className="mt-3 mb-0 max-w-[70ch] text-sm text-muted">
        {t("intro", { benchmark: symbol, benchmarkNote: t(`benchmarkNote.${symbol}` as "benchmarkNote.SPY") })}
      </p>

      {option === null || stats === null || asset === null || market === null ? (
        <div className="mt-6 rounded-card border border-caution/30 bg-caution-soft px-5 py-6">
          <p className="m-0 text-sm font-bold text-ink">
            {t("comparisonUnavailable", { symbol, period })}
          </p>
          <p className="mt-1 mb-0 text-sm text-muted">
            {t(`unavailable.${record.reason ?? "insufficient_overlap"}` as "unavailable.missing_prices", {
              symbol,
            })}
          </p>
          <button
            type="button"
            onClick={() => setSymbol(benchmark)}
            className="mt-3 rounded-md border border-line bg-panel px-3 py-1.5 text-xs font-bold text-ink"
          >
            {t("backToDefault", { benchmark })}
          </button>
        </div>
      ) : (
        <>
          <div className="lens-grid mt-6 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_260px]">
            <GrowthChart points={option.growth} benchmark={symbol} ticker={ticker} />
            <div className="flex min-w-0 flex-col gap-2 rounded-card bg-accent-soft p-5">
              <span className="text-[11px] font-bold tracking-wide text-accent uppercase">
                {t("endingValue")}
              </span>
              <strong className="lens-figure text-3xl break-words text-ink">
                {money(stats.ending_value)}
              </strong>
              <small className="text-xs text-muted">
                {t("endingFrom", {
                  initial: money(stats.initial_investment) ?? "",
                  start: option.period.start,
                  end: option.period.end,
                })}
              </small>
              <div className="mt-auto flex flex-col gap-1 border-t border-line pt-4 text-xs text-muted">
                <span>{t("relative", { benchmark: symbol })}</span>
                <b className="lens-figure text-lg text-ink">
                  {signedPercent(stats.relative_total_return)}
                </b>
                <span>
                  {t("bothReturns", {
                    ticker,
                    asset: signedPercent(asset.total_return) ?? "",
                    benchmark: symbol,
                    market: signedPercent(market.total_return) ?? "",
                  })}
                </span>
              </div>
            </div>
          </div>

          <div className="lens-grid mt-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <StatCard
              label={t("metric.totalReturn")}
              value={signedPercent(asset.total_return)}
              context={t("metric.periodContext", { start: option.period.start, end: option.period.end })}
              missingLabel={t("notAvailable")}
              tone={asset.total_return >= 0 ? "positive" : "critical"}
            />
            <StatCard
              label={t("metric.cagr")}
              value={signedPercent(asset.cagr)}
              context={t("metric.cagrContext")}
              missingLabel={t("notAvailable")}
            />
            <StatCard
              label={t("metric.volatility")}
              value={percent(asset.annualized_volatility)}
              context={t("metric.volatilityContext")}
              missingLabel={t("notAvailable")}
            />
            <StatCard
              label={t("metric.maxDrawdown")}
              value={signedPercent(asset.max_drawdown)}
              context={
                asset.max_drawdown_date
                  ? t("metric.troughOn", { date: asset.max_drawdown_date })
                  : null
              }
              missingLabel={t("notAvailable")}
              tone="caution"
            />
            <StatCard
              label={t("metric.beta", { benchmark: symbol })}
              value={multiple(stats.beta)}
              context={t("metric.betaContext")}
              missingLabel={t("notAvailable")}
            />
            <StatCard
              label={t("metric.correlation", { benchmark: symbol })}
              value={multiple(stats.correlation)}
              context={t("metric.sessions", { count: count(stats.observations) ?? "" })}
              missingLabel={t("notAvailable")}
            />
          </div>

          <div className="mt-4 flex flex-col gap-2 border-l-[3px] border-caution bg-caution-soft px-4 py-3 text-xs text-ink md:flex-row md:gap-6">
            <strong className="shrink-0 font-bold">{t("riskNoteLabel")}</strong>
            <span>
              {t("riskNote", {
                drawdown: signedPercent(asset.max_drawdown) ?? "",
                worst: signedPercent(asset.worst_day) ?? "",
              })}
            </span>
          </div>

          {coverage && coverage.status !== "full" ? (
            <p className="mt-3 mb-0 text-xs text-muted">
              {t("coveragePartial", {
                requested: coverage.requested_start ?? "",
                start: coverage.start ?? "",
                end: coverage.end ?? "",
                sessions: count(coverage.observations) ?? "",
              })}
            </p>
          ) : null}

          <p className="mt-3 mb-0 text-xs text-muted">
            {t("scopeNote", { benchmark, selected: symbol })}
          </p>
          <p className="mt-1 mb-0 text-xs text-muted">{t("boundary")}</p>
        </>
      )}
    </section>
  );
}
