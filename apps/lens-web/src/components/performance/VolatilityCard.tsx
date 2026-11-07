import { getTranslations } from "next-intl/server";
import type { VolatilityForecast } from "@/lib/contracts/snapshot";
import { percent } from "@/lib/format";

/**
 * How wide a range the next twenty sessions are expected to cover, beside what
 * this issuer usually does.
 *
 * Present only when a forecaster passed its out-of-sample coverage gate, which
 * is why the whole card disappears rather than degrading: the engine deletes
 * the file when nothing earned it. A band and a horizon, never a direction.
 */
export async function VolatilityCard({
  forecast,
}: {
  forecast: VolatilityForecast | null | undefined;
}) {
  const t = await getTranslations("volatility");
  if (!forecast || forecast.median === null || forecast.median === undefined) return null;

  const median = forecast.median;
  const low = forecast.band_low ?? median;
  const high = forecast.band_high ?? median;
  const usual = forecast.issuer_median ?? 0;
  // A fixed span, so a narrow band looks narrow and two companies' cards are
  // comparable at a glance.
  const span = Math.max(high, usual, 0.6) * 1.05;
  const at = (value: number) => Math.max(0, Math.min(100, (100 * value) / span));
  const state = forecast.state ?? "typical for this issuer";
  const stateKey = state.replace(/\s+/g, "_");

  return (
    <section
      id="volatility"
      className="scroll-mt-24 border-t border-line py-10 md:py-12"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
        <div className="min-w-0">
          <p className="lens-eyebrow m-0 mb-2">{t("eyebrow")}</p>
          <h2 className="lens-serif m-0 text-2xl text-balance md:text-3xl">
            {t("title", { sessions: forecast.horizon_sessions ?? 20 })}
          </h2>
        </div>
        <span className="shrink-0 rounded-full border border-line bg-panel-muted px-2.5 py-1 text-[11px] font-bold tracking-wide text-muted uppercase">
          {t(`state.${stateKey}` as "state.typical_for_this_issuer")}
        </span>
      </div>

      <div className="mt-6">
        <div
          className="relative h-11 rounded-md border border-line bg-panel"
          role="img"
          aria-label={t("alt", {
            low: percent(low, 0) ?? "",
            high: percent(high, 0) ?? "",
            median: percent(median, 0) ?? "",
            usual: percent(usual, 0) ?? "",
          })}
        >
          <div
            className="absolute inset-y-0 border-x border-accent/40 bg-accent-soft"
            style={{ left: `${at(low)}%`, width: `${Math.max(1, at(high) - at(low))}%` }}
          />
          <div className="absolute inset-y-0 w-0.5 bg-accent" style={{ left: `${at(median)}%` }} />
          {usual > 0 ? (
            <div
              className="absolute -inset-y-1 w-px border-l border-dashed border-caution"
              style={{ left: `${at(usual)}%` }}
            />
          ) : null}
        </div>
        <div className="mt-1.5 flex justify-between text-[11px] text-muted">
          <span>0%</span>
          <span>{percent(span, 0)}</span>
        </div>
      </div>

      <dl className="lens-grid mt-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {[
          { key: "median", value: percent(median, 0), label: t("median") },
          { key: "band", value: `${percent(low, 0)}–${percent(high, 0)}`, label: t("band") },
          { key: "usual", value: percent(usual, 0), label: t("usual") },
        ].map((row) => (
          <div
            key={row.key}
            className="flex min-w-0 flex-col gap-1 rounded-card border border-line bg-panel-muted p-4"
          >
            <dt className="text-[11px] text-muted">{row.label}</dt>
            <dd className="lens-figure m-0 text-2xl break-words">{row.value}</dd>
          </div>
        ))}
      </dl>

      <p className="mt-4 mb-0 text-xs text-muted">
        {forecast.coverage_80 !== null && forecast.coverage_80 !== undefined
          ? t("coverage", { value: percent(forecast.coverage_80, 0) ?? "" })
          : null}{" "}
        {t("boundary")}
      </p>
    </section>
  );
}
