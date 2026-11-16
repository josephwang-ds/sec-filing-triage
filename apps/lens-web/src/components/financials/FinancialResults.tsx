import { getLocale, getTranslations } from "next-intl/server";
import type { FiledMetric, FinancialResults as Report } from "@/lib/contracts/snapshot";
import { Section } from "@/components/ui/Section";
import { EmptyState } from "@/components/ui/EmptyState";
import { SourceLink } from "@/components/ui/SourceLink";
import { filedMoney, points, signedPercent } from "@/lib/format";

/**
 * Module B. The latest filed financial report, as filed.
 *
 * Every figure, period and growth rate here comes from
 * `company_lens.financial_results`, which reads them out of one filing and
 * refuses to mix a cumulative half-year fact into a quarter. Nothing is
 * computed in the browser. Two absences are stated rather than hidden: a growth
 * rate the engine withheld because the prior base was a loss or a zero, and a
 * peer reference it withheld because fewer than five eligible issuers were
 * found -- a median of two is not a category rate.
 */
export async function FinancialResults({ report }: { report: Report | null | undefined }) {
  const t = await getTranslations("financials");
  const locale = await getLocale();

  if (!report || report.status === "unavailable") {
    return (
      <Section id="financials" eyebrow={t("eyebrow")} title={t("title")}>
        <EmptyState title={t("empty.title")} body={t("empty.body")} footnote={t("empty.footnote")} />
      </Section>
    );
  }

  const kind = report.period_kind === "annual" ? t("annual") : t("quarterly");
  const metrics = report.metrics;

  return (
    <Section
      id="financials"
      eyebrow={t("eyebrow")}
      title={t("title")}
      intro={t("intro", {
        kind,
        form: report.form ?? "",
        periodEnd: report.period_end ?? "",
        filed: report.filed ?? "",
      })}
      aside={
        report.source_url ? (
          <SourceLink href={report.source_url}>{t("sourceFiling", { form: report.form ?? "" })}</SourceLink>
        ) : null
      }
    >
      {metrics.length === 0 ? (
        <EmptyState title={t("metadataOnly.title")} body={t("metadataOnly.body")} />
      ) : (
        <div className="lens-grid grid grid-cols-1 gap-3 lg:grid-cols-2">
          {metrics.map((metric) => (
            <MetricCard key={metric.id} metric={metric} locale={locale} t={t} />
          ))}
        </div>
      )}
      <p className="mt-5 mb-0 text-xs text-muted">{t("boundary")}</p>
    </Section>
  );
}

type Translator = Awaited<ReturnType<typeof getTranslations<"financials">>>;

function MetricCard({
  metric,
  locale,
  t,
}: {
  metric: FiledMetric;
  locale: string;
  t: Translator;
}) {
  const value = filedMoney(metric.value, metric.unit, locale);
  const prior = filedMoney(metric.prior_value, metric.unit, locale);
  const yoy = signedPercent(metric.yoy);
  const label = t(`metric.${metric.id}.label` as "metric.revenue.label");
  const definition = t(`metric.${metric.id}.definition` as "metric.revenue.definition");
  const reference = metric.reference;

  return (
    <article className="flex min-w-0 flex-col gap-3 rounded-card border border-line bg-panel-muted p-5">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="m-0 text-sm font-bold tracking-wide text-muted uppercase">{label}</h3>
        {yoy ? (
          <span
            className={[
              "rounded-full px-2 py-0.5 text-xs font-bold",
              (metric.yoy ?? 0) >= 0
                ? "bg-positive-soft text-positive"
                : "bg-critical-soft text-critical",
            ].join(" ")}
          >
            {t("yoyBadge", { value: yoy })}
          </span>
        ) : (
          <span className="rounded-full bg-panel px-2 py-0.5 text-xs text-muted">
            {t("yoyUnavailable")}
          </span>
        )}
      </header>

      <strong className="lens-figure text-3xl break-words">{value}</strong>
      <p className="m-0 text-xs text-muted">
        {t("currentPeriod", { start: metric.start, end: metric.end, unit: metric.unit })}
      </p>
      {prior && metric.prior_start ? (
        <p className="m-0 text-xs text-muted">
          {t("priorPeriod", {
            value: prior,
            start: metric.prior_start,
            end: metric.prior_end ?? "",
          })}
        </p>
      ) : (
        <p className="m-0 text-xs text-muted">{t("noPrior")}</p>
      )}
      {!yoy && metric.change !== null && metric.change !== undefined ? (
        <p className="m-0 text-xs break-words text-muted">
          {t("yoyWithheld", { change: filedMoney(metric.change, metric.unit, locale) ?? "" })}
        </p>
      ) : null}
      <p className="m-0 text-xs text-muted">{definition}</p>

      {reference ? (
        <div className="rounded-md border border-line bg-panel p-3">
          {reference.status === "available" ? (
            <p className="m-0 text-xs text-ink">
              {t("reference.available", {
                group: reference.sic_group ?? "",
                median: signedPercent(reference.median_yoy) ?? "",
                n: reference.n,
                gap: points(reference.gap_pp) ?? "",
              })}
            </p>
          ) : (
            <p className="m-0 text-xs text-muted">
              {t("reference.unavailable")}{" "}
              {t(`reference.reason.${reference.reason ?? "insufficient_sample"}` as "reference.reason.insufficient_sample", {
                n: reference.n,
                minimum: reference.minimum,
              })}
            </p>
          )}
          <details className="mt-2">
            <summary className="cursor-pointer text-xs font-bold text-accent">
              {t("reference.method")}
            </summary>
            <p className="mt-2 mb-0 text-xs text-muted">
              {t("reference.methodBody", { asOf: reference.as_of ?? "" })}
            </p>
            {reference.members.length ? (
              <ul className="mt-2 mb-0 flex list-none flex-col gap-1 p-0">
                {reference.members.map((member) => (
                  <li key={member.ticker} className="min-w-0">
                    <SourceLink href={member.source_url}>
                      {`${member.ticker} · ${member.period_end} · ${signedPercent(member.yoy) ?? ""}`}
                    </SourceLink>
                  </li>
                ))}
              </ul>
            ) : null}
          </details>
        </div>
      ) : null}

      <details>
        <summary className="cursor-pointer text-xs font-bold text-accent">
          {t("conceptLabel")}
        </summary>
        <p className="mt-2 mb-0 text-xs text-muted">{t("conceptBody")}</p>
        {/* The accounting concept stays in its own vocabulary: a translated
            us-gaap tag is not a us-gaap tag. */}
        <code className="mt-1 block text-xs break-all text-ink">{metric.concept}</code>
      </details>
    </article>
  );
}
