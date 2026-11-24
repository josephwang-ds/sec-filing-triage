import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { Section } from "@/components/ui/Section";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageNav } from "@/components/research/PageNav";
import { EvidenceTable } from "@/components/research/EvidenceTable";
import { researchEvidence } from "@/lib/data/research";
import { count, percent } from "@/lib/format";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "overview" });
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    alternates: { canonical: `/${locale}/overview`, languages: { zh: "/zh/overview", en: "/en/overview" } },
  };
}

/**
 * The project in ordinary words, in both languages.
 *
 * Jargon is absent rather than simplified, which is the rule the Python page
 * set and the one most easily lost in translation. Every figure is read from
 * the evidence package at build time; none is written into this file.
 */
export default async function OverviewPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("overview");
  const evidence = researchEvidence();
  const metrics = evidence.metrics;

  const sections = [
    { id: "problem", label: t("nav.problem") },
    { id: "sources", label: t("nav.sources") },
    { id: "does", label: t("nav.does") },
    { id: "results", label: t("nav.results") },
    { id: "leakage", label: t("nav.leakage") },
    { id: "failures", label: t("nav.failures") },
    { id: "product", label: t("nav.product") },
  ];

  const ladder = evidence.ladder;
  const naive = ladder[0] ?? null;
  const honest = ladder.length ? ladder[ladder.length - 1] : null;

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
          <Section id="problem" eyebrow={t("nav.problem")} title={t("problem.title")}>
            <div className="flex max-w-[70ch] flex-col gap-3 text-sm">
              <p className="m-0">{t("problem.body1")}</p>
              <p className="m-0">{t("problem.body2")}</p>
              {metrics ? (
                <p className="m-0">
                  {t("problem.scale", {
                    filings: count(metrics.n_events) ?? "",
                    sessions: count(metrics.sessions) ?? "",
                    median: count(metrics.filings_per_session_median ?? null) ?? "",
                  })}
                </p>
              ) : null}
            </div>
          </Section>

          <Section id="sources" eyebrow={t("nav.sources")} title={t("sources.title")}>
            <ul className="lens-grid m-0 grid list-none grid-cols-1 gap-3 p-0 md:grid-cols-3">
              {["filings", "prices", "fundamentals"].map((key) => (
                <li
                  key={key}
                  className="flex min-w-0 flex-col gap-2 rounded-card border border-line bg-panel-muted p-4"
                >
                  <h3 className="m-0 text-sm font-bold">{t(`sources.${key}.title` as "sources.filings.title")}</h3>
                  <p className="m-0 text-sm text-muted">
                    {t(`sources.${key}.body` as "sources.filings.body")}
                  </p>
                </li>
              ))}
            </ul>
            <p className="mt-4 mb-0 max-w-[70ch] text-sm text-muted">{t("sources.note")}</p>
          </Section>

          <Section id="does" eyebrow={t("nav.does")} title={t("does.title")}>
            <div className="lens-grid grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="min-w-0 rounded-card border border-line bg-panel-muted p-5">
                <h3 className="m-0 mb-2 text-sm font-bold">{t("does.doesTitle")}</h3>
                <ul className="m-0 flex list-disc flex-col gap-1.5 pl-5 text-sm">
                  {["rank", "measure", "publish"].map((key) => (
                    <li key={key}>{t(`does.does.${key}` as "does.does.rank")}</li>
                  ))}
                </ul>
              </div>
              <div className="min-w-0 rounded-card border border-caution/30 bg-caution-soft p-5">
                <h3 className="m-0 mb-2 text-sm font-bold">{t("does.notTitle")}</h3>
                <ul className="m-0 flex list-disc flex-col gap-1.5 pl-5 text-sm">
                  {["advice", "direction", "returns"].map((key) => (
                    <li key={key}>{t(`does.not.${key}` as "does.not.advice")}</li>
                  ))}
                </ul>
              </div>
            </div>
          </Section>

          <Section id="results" eyebrow={t("nav.results")} title={t("results.title")}>
            {metrics ? (
              <>
                <div className="lens-grid grid grid-cols-1 gap-3 sm:grid-cols-3">
                  {[
                    {
                      key: "model",
                      value: percent(metrics.daily_precision_at_5, 1),
                      label: t("results.model"),
                    },
                    {
                      key: "random",
                      value: percent(metrics.daily_random_precision_at_5, 1),
                      label: t("results.random"),
                    },
                    {
                      key: "sessions",
                      value: count(metrics.daily_sessions_at_5 ?? metrics.sessions),
                      label: t("results.sessions"),
                    },
                  ].map((row) => (
                    <div
                      key={row.key}
                      className="flex min-w-0 flex-col gap-1 rounded-card border border-line bg-panel-muted p-4"
                    >
                      <strong className="lens-figure text-3xl">{row.value}</strong>
                      <span className="text-xs text-muted">{row.label}</span>
                    </div>
                  ))}
                </div>
                {/* The definition, kept adjacent to the number. It is the
                    average share of the top five that mattered -- not the
                    chance of finding at least one, which is what a reader
                    assumes when the definition is a footnote. */}
                <p className="mt-4 mb-0 max-w-[70ch] rounded-card border border-accent/30 bg-accent-soft px-4 py-3 text-sm">
                  <strong>{t("results.definitionLabel")}</strong> {t("results.definition")}
                </p>
                <p className="mt-3 mb-0 max-w-[70ch] text-sm text-muted">
                  {t("results.interval", {
                    low: percent(metrics.average_precision_ci_low ?? null, 1) ?? "",
                    high: percent(metrics.average_precision_ci_high ?? null, 1) ?? "",
                    draws: count(metrics.bootstrap_draws ?? null) ?? "",
                  })}
                </p>
              </>
            ) : (
              <EmptyState title={t("noEvidence.title")} body={t("noEvidence.body")} />
            )}
          </Section>

          <Section id="leakage" eyebrow={t("nav.leakage")} title={t("leakage.title")}>
            <div className="flex max-w-[70ch] flex-col gap-3 text-sm">
              <p className="m-0">{t("leakage.body1")}</p>
              {naive && honest ? (
                <p className="m-0">
                  {t("leakage.body2", {
                    naive: percent(naive.daily_precision_at_5, 1) ?? "",
                    honest: percent(honest.daily_precision_at_5, 1) ?? "",
                  })}
                </p>
              ) : null}
            </div>
            {ladder.length ? (
              <div className="mt-5">
                <EvidenceTable
                  caption={t("leakage.caption")}
                  headers={[
                    t("leakage.column.stage"),
                    t("leakage.column.daily"),
                    t("leakage.column.ap"),
                    t("leakage.column.impossible"),
                  ]}
                  rows={ladder.map((row) => [
                    row.stage,
                    percent(row.daily_precision_at_5, 1),
                    percent(row.average_precision, 1),
                    percent(row.impossible_share, 0),
                  ])}
                />
              </div>
            ) : null}
          </Section>

          <Section id="failures" eyebrow={t("nav.failures")} title={t("failures.title")}>
            <p className="m-0 mb-4 max-w-[70ch] text-sm text-muted">{t("failures.intro")}</p>
            <ul className="m-0 flex list-none flex-col gap-3 p-0">
              {["text", "selfRelative", "volatility"].map((key) => (
                <li
                  key={key}
                  className="min-w-0 rounded-card border border-line bg-panel-muted p-4"
                >
                  <h3 className="m-0 mb-1 text-sm font-bold">
                    {t(`failures.${key}.title` as "failures.text.title")}
                  </h3>
                  <p className="m-0 text-sm text-muted">
                    {t(`failures.${key}.body` as "failures.text.body")}
                  </p>
                </li>
              ))}
            </ul>
          </Section>

          <Section id="product" eyebrow={t("nav.product")} title={t("product.title")}>
            <p className="m-0 mb-4 max-w-[70ch] text-sm text-muted">{t("product.intro")}</p>
            <div className="flex flex-wrap gap-3">
              <Link
                href="/"
                className="rounded-md bg-ink px-4 py-2 text-sm font-bold text-paper"
              >
                {t("product.openLens")}
              </Link>
              <Link
                href="/research"
                className="rounded-md border border-line px-4 py-2 text-sm font-bold text-ink"
              >
                {t("product.openResearch")}
              </Link>
              <a
                href="https://github.com/josephwang-ds/sec-filing-triage"
                target="_blank"
                rel="noreferrer noopener"
                className="rounded-md border border-line px-4 py-2 text-sm font-bold text-ink"
              >
                {t("product.source")}
              </a>
            </div>
          </Section>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
