import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { Section } from "@/components/ui/Section";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageNav } from "@/components/research/PageNav";
import { EvidenceTable } from "@/components/research/EvidenceTable";
import { AuditSections } from "@/components/research/AuditSections";
import { researchEvidence } from "@/lib/data/research";
import { count, multiple, percent } from "@/lib/format";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "research" });
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    alternates: { canonical: `/${locale}/research`, languages: { zh: "/zh/research", en: "/en/research" } },
  };
}

/**
 * Method and audit, for a reader who wants the vocabulary.
 *
 * Same evidence files as the overview page, read the same way. Where the two
 * pages state the same number they state it from one source, so they cannot
 * drift apart.
 */
export default async function ResearchPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("research");
  const evidence = researchEvidence();
  const metrics = evidence.metrics;
  const manifest = evidence.manifest;
  const config = (manifest?.pipeline_config ?? {}) as Record<string, string | number>;

  const sections = [
    { id: "question", label: t("nav.question") },
    { id: "method", label: t("nav.method") },
    { id: "pit", label: t("nav.pit") },
    { id: "leakage", label: t("nav.leakage") },
    { id: "metrics", label: t("nav.metrics") },
    { id: "baselines", label: t("nav.baselines") },
    { id: "capacity", label: t("nav.capacity") },
    { id: "tradability", label: t("nav.tradability") },
    { id: "models", label: t("nav.models") },
    { id: "calibration", label: t("nav.calibration") },
    { id: "volatility", label: t("nav.volatility") },
    { id: "ablations", label: t("nav.ablations") },
    { id: "limitations", label: t("nav.limitations") },
    { id: "provenance", label: t("nav.provenance") },
    { id: "glossary", label: t("nav.glossary") },
  ];

  if (!evidence.available) {
    return (
      <>
        <SiteHeader />
        <main id="main" className="lens-shell py-16">
          <EmptyState title={t("noEvidence.title")} body={t("noEvidence.body")} />
        </main>
        <SiteFooter />
      </>
    );
  }

  return (
    <>
      <SiteHeader />
      <main id="main" className="lens-shell pb-16">
        <section className="flex flex-col gap-4 py-10 md:py-14">
          <p className="lens-eyebrow m-0">{t("eyebrow")}</p>
          <h1 className="lens-serif m-0 max-w-[26ch] text-4xl text-balance md:text-5xl">
            {t("title")}
          </h1>
          <p className="m-0 max-w-[68ch] text-base text-muted md:text-lg">{t("lede")}</p>
        </section>

        <PageNav label={t("nav.label")} sections={sections} />

        <div className="flex flex-col gap-6">
          <Section id="question" eyebrow={t("nav.question")} title={t("question.title")}>
            <div className="flex max-w-[70ch] flex-col gap-3 text-sm">
              <p className="m-0">{t("question.body1")}</p>
              <p className="m-0">{t("question.body2")}</p>
            </div>
          </Section>

          <Section id="method" eyebrow={t("nav.method")} title={t("method.title")}>
            <dl className="lens-grid m-0 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {[
                { key: "label", value: t("method.labelValue", { threshold: String(config.reaction_threshold ?? "") }) },
                { key: "window", value: t("method.windowValue", { sessions: String(config.event_window_sessions ?? "") }) },
                { key: "estimation", value: t("method.estimationValue", { sessions: String(config.estimation_sessions ?? ""), gap: String(config.estimation_gap_sessions ?? "") }) },
                { key: "validation", value: String(config.validation ?? "") },
              ].map((row) => (
                <div
                  key={row.key}
                  className="flex min-w-0 flex-col gap-1 rounded-card border border-line bg-panel-muted p-4"
                >
                  <dt className="text-[11px] font-bold tracking-wide text-muted uppercase">
                    {t(`method.${row.key}` as "method.label")}
                  </dt>
                  <dd className="m-0 text-sm break-words">{row.value}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-4 mb-0 max-w-[70ch] text-sm text-muted">
              {t("method.reaction", { convention: String(config.reaction_measured_from ?? "") })}
            </p>
          </Section>

          <Section id="pit" eyebrow={t("nav.pit")} title={t("pit.title")}>
            <ul className="m-0 flex list-disc flex-col gap-2 pl-5 text-sm">
              {["entry", "features", "universe", "history"].map((key) => (
                <li key={key} className="max-w-[70ch]">
                  {t(`pit.${key}` as "pit.entry")}
                </li>
              ))}
            </ul>
          </Section>

          <Section id="leakage" eyebrow={t("nav.leakage")} title={t("leakage.title")} intro={t("leakage.intro")}>
            <EvidenceTable
              caption={t("leakage.caption")}
              headers={[
                t("leakage.column.stage"),
                t("leakage.column.events"),
                t("leakage.column.ap"),
                t("leakage.column.auc"),
                t("leakage.column.daily"),
                t("leakage.column.lift"),
                t("leakage.column.impossible"),
              ]}
              rows={evidence.ladder.map((row) => [
                row.stage,
                count(row.n_events),
                percent(row.average_precision, 1),
                multiple(row.roc_auc, 3),
                percent(row.daily_precision_at_5, 1),
                multiple(row.daily_lift_at_5, 2),
                percent(row.impossible_share, 0),
              ])}
            />
            <ul className="mt-4 mb-0 flex list-none flex-col gap-2 p-0 text-xs text-muted">
              {evidence.ladder.map((row) => (
                <li key={row.stage} className="max-w-[80ch]">
                  <strong className="text-ink">{row.stage}:</strong> {row.note}
                </li>
              ))}
            </ul>
          </Section>

          <Section id="metrics" eyebrow={t("nav.metrics")} title={t("metrics.title")}>
            {metrics ? (
              <>
                <EvidenceTable
                  caption={t("metrics.caption")}
                  headers={[t("metrics.column.metric"), t("metrics.column.value"), t("metrics.column.meaning")]}
                  rows={[
                    [
                      t("metrics.dailyPrecision"),
                      percent(metrics.daily_precision_at_5, 1),
                      t("metrics.dailyPrecisionMeaning"),
                    ],
                    [
                      t("metrics.randomPrecision"),
                      percent(metrics.daily_random_precision_at_5, 1),
                      t("metrics.randomPrecisionMeaning"),
                    ],
                    [
                      t("metrics.averagePrecision"),
                      percent(metrics.average_precision, 1),
                      t("metrics.averagePrecisionMeaning"),
                    ],
                    [t("metrics.rocAuc"), multiple(metrics.roc_auc, 3), t("metrics.rocAucMeaning")],
                    [
                      t("metrics.baseRate"),
                      percent(metrics.base_rate, 1),
                      t("metrics.baseRateMeaning"),
                    ],
                  ]}
                />
                <p className="mt-4 mb-0 max-w-[70ch] rounded-card border border-accent/30 bg-accent-soft px-4 py-3 text-sm">
                  <strong>{t("metrics.definitionLabel")}</strong> {t("metrics.definition")}
                </p>
                <p className="mt-3 mb-0 max-w-[70ch] text-sm text-muted">
                  {t("metrics.uncertainty", {
                    method: manifest?.uncertainty?.method ?? "",
                    draws: count(manifest?.uncertainty?.draws ?? null) ?? "",
                    sessions: count(manifest?.uncertainty?.sessions ?? null) ?? "",
                    apLow: percent(metrics.average_precision_ci_low ?? null, 1) ?? "",
                    apHigh: percent(metrics.average_precision_ci_high ?? null, 1) ?? "",
                  })}
                </p>
              </>
            ) : null}
          </Section>

          <Section id="baselines" eyebrow={t("nav.baselines")} title={t("baselines.title")} intro={t("baselines.intro")}>
            {metrics ? (
              <EvidenceTable
                caption={t("baselines.caption")}
                headers={[t("baselines.column.rule"), t("baselines.column.daily")]}
                rows={[
                  [t("baselines.model"), percent(metrics.daily_precision_at_5, 1)],
                  [t("baselines.random"), percent(metrics.daily_random_precision_at_5, 1)],
                  [t("baselines.arrival"), percent(metrics.daily_arrival_precision_at_5 ?? null, 1)],
                  [t("baselines.item202"), percent(metrics.daily_item_202_precision_at_5 ?? null, 1)],
                  [t("baselines.oracle"), percent(metrics.daily_oracle_precision_at_5 ?? null, 1)],
                ]}
              />
            ) : null}
          </Section>

          <AuditSections />

          <Section id="ablations" eyebrow={t("nav.ablations")} title={t("ablations.title")} intro={t("ablations.intro")}>
            {evidence.nlpAblation.length ? (
              <EvidenceTable
                caption={t("ablations.caption")}
                headers={Object.keys(evidence.nlpAblation[0] ?? {}).slice(0, 5)}
                rows={evidence.nlpAblation.map((row) =>
                  Object.values(row)
                    .slice(0, 5)
                    .map((value) => value),
                )}
              />
            ) : (
              <EmptyState compact title={t("ablations.missingTitle")} body={t("ablations.missingBody")} />
            )}
          </Section>

          <Section id="limitations" eyebrow={t("nav.limitations")} title={t("limitations.title")}>
            <ul className="m-0 flex list-disc flex-col gap-2 pl-5 text-sm">
              {["universe", "costs", "magnitude", "coverage", "generalisation"].map((key) => (
                <li key={key} className="max-w-[70ch]">
                  {t(`limitations.${key}` as "limitations.universe")}
                </li>
              ))}
            </ul>
          </Section>

          <Section id="provenance" eyebrow={t("nav.provenance")} title={t("provenance.title")}>
            <dl className="m-0 grid grid-cols-1 gap-2 text-sm sm:grid-cols-[auto_minmax(0,1fr)]">
              {[
                { term: t("provenance.exported"), value: manifest?.exported_at ?? "—" },
                { term: t("provenance.schema"), value: manifest?.schema_version ?? "—" },
                ...Object.entries(manifest?.inputs ?? {}).map(([name, input]) => ({
                  term: name,
                  value: `${count(input.rows ?? null) ?? "—"} ${t("provenance.rows")} · sha256 ${String(input.sha256 ?? "").slice(0, 12)}…`,
                })),
              ].map((row) => (
                <div key={row.term} className="contents">
                  <dt className="font-bold">{row.term}</dt>
                  <dd className="m-0 break-all text-muted">{row.value}</dd>
                </div>
              ))}
            </dl>
          </Section>

          <Section id="glossary" eyebrow={t("nav.glossary")} title={t("glossary.title")}>
            <dl className="m-0 flex flex-col gap-3">
              {["precision", "averagePrecision", "rocAuc", "baseRate", "walkForward", "purged", "pointInTime"].map(
                (key) => (
                  <div key={key} className="min-w-0 rounded-card border border-line bg-panel-muted p-4">
                    <dt className="m-0 text-sm font-bold">
                      {t(`glossary.${key}.term` as "glossary.precision.term")}
                    </dt>
                    <dd className="m-0 mt-1 text-sm text-muted">
                      {t(`glossary.${key}.definition` as "glossary.precision.definition")}
                    </dd>
                  </div>
                ),
              )}
            </dl>
          </Section>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
