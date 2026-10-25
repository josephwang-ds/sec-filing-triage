import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { routing } from "@/i18n/routing";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { CompanyHero } from "@/components/company/CompanyHero";
import { CompanyBrief } from "@/components/company/CompanyBrief";
import { CompanyNews } from "@/components/company/CompanyNews";
import { FinancialResults } from "@/components/financials/FinancialResults";
import { PerformanceSection } from "@/components/performance/PerformanceSection";
import { VolatilityCard } from "@/components/performance/VolatilityCard";
import { FilingsSection } from "@/components/filings/FilingsSection";
import { DisclosureSignalCard } from "@/components/filings/DisclosureSignalCard";
import { EventsSection } from "@/components/events/EventsSection";
import { AskSection } from "@/components/ai/AskSection";
import { getSnapshot, snapshotTickers } from "@/lib/data/snapshots";
import { isoDate } from "@/lib/format";

/**
 * The company workspace: one page, six modules, in the order a reader needs
 * them -- who this is, what was filed, what the history looks like, what the
 * disclosures say, what happened lately, and then questions.
 *
 * Every module is handed engine output and renders what is there. A module with
 * nothing to render says so in its own words; none of them is hidden, because a
 * silently missing section is indistinguishable from a section that was never
 * supposed to exist.
 */
export function generateStaticParams() {
  return routing.locales.flatMap((locale) =>
    snapshotTickers().map((ticker) => ({ locale, ticker: ticker.toLowerCase() })),
  );
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string; ticker: string }>;
}): Promise<Metadata> {
  const { locale, ticker } = await params;
  const snapshot = getSnapshot(ticker);
  if (!snapshot) return {};
  const t = await getTranslations({ locale, namespace: "company" });
  const name = snapshot.profile.display_name ?? snapshot.company_name;
  const summary =
    (locale === "zh" ? snapshot.profile.summary_zh : snapshot.profile.summary) ??
    snapshot.profile.summary ??
    undefined;
  return {
    title: `${snapshot.ticker} · ${name}`,
    description: summary ?? t("metaDescription", { name }),
    alternates: {
      canonical: `/${locale}/company/${snapshot.ticker.toLowerCase()}`,
      languages: {
        zh: `/zh/company/${snapshot.ticker.toLowerCase()}`,
        en: `/en/company/${snapshot.ticker.toLowerCase()}`,
      },
    },
  };
}

export default async function CompanyPage({
  params,
}: {
  params: Promise<{ locale: string; ticker: string }>;
}) {
  const { locale, ticker } = await params;
  setRequestLocale(locale);
  const snapshot = getSnapshot(ticker);
  if (!snapshot) notFound();

  const t = await getTranslations("company");
  const defaultPeriod =
    Object.keys(snapshot.period_options).find((label) => label === "5Y") ??
    Object.keys(snapshot.period_options)[0] ??
    "5Y";

  const sections = [
    { id: "brief", label: t("nav.brief") },
    { id: "financials", label: t("nav.financials") },
    { id: "performance", label: t("nav.performance") },
    { id: "filings", label: t("nav.filings") },
    { id: "events", label: t("nav.events") },
    { id: "ask", label: t("nav.ask") },
  ];

  return (
    <>
      <SiteHeader symbol={snapshot.ticker} />
      <main id="main" className="lens-shell pb-16">
        <CompanyHero snapshot={snapshot} />

        <nav
          aria-label={t("nav.label")}
          className="mb-8 flex gap-1 overflow-x-auto border-y border-line py-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          {sections.map((section) => (
            <a
              key={section.id}
              href={`#${section.id}`}
              className="shrink-0 rounded-md px-2.5 py-1 text-xs font-bold whitespace-nowrap text-muted hover:bg-panel hover:text-ink"
            >
              {section.label}
            </a>
          ))}
        </nav>

        <div className="flex flex-col gap-6">
          <CompanyBrief snapshot={snapshot} />
          <FinancialResults report={snapshot.financial_results} />
          <PerformanceSection
            ticker={snapshot.ticker}
            benchmark={snapshot.benchmark}
            periods={snapshot.period_options}
            comparisons={snapshot.benchmark_comparisons}
            defaultPeriod={defaultPeriod}
          />
          <VolatilityCard forecast={snapshot.volatility_forecast} />
          <FilingsSection snapshot={snapshot} />
          <DisclosureSignalCard signal={snapshot.disclosure_signal} />
          <EventsSection ticker={snapshot.ticker} />
          <CompanyNews snapshot={snapshot} />
          <AskSection ticker={snapshot.ticker} evidenceAsOf={snapshot.as_of} />
        </div>
      </main>
      <SiteFooter
        asOf={snapshot.as_of}
        marketThrough={isoDate(snapshot.market.price_date) ?? undefined}
      />
    </>
  );
}
