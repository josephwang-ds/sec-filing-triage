import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { CompanyFinder } from "@/components/company/CompanyFinder";
import { featuredCompanies, listCompanies, manifest } from "@/lib/data/snapshots";
import { percentagePoints } from "@/lib/format";
import { getSnapshot } from "@/lib/data/snapshots";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "home" });
  return { title: t("metaTitle"), description: t("metaDescription") };
}

export default async function HomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("home");
  const companies = listCompanies();
  const featured = featuredCompanies();
  const data = manifest();

  const evidence = [
    { key: "filings", href: "/research" as const },
    { key: "prices", href: "/research" as const },
    { key: "fundamentals", href: "/research" as const },
  ];

  return (
    <>
      <SiteHeader />
      <main id="main" className="lens-shell pb-16">
        <section className="flex flex-col gap-4 py-10 md:py-14">
          <p className="lens-eyebrow m-0">{t("eyebrow")}</p>
          <h1 className="lens-serif m-0 max-w-[24ch] text-4xl text-balance md:text-6xl">
            {t("title")}
          </h1>
          <p className="m-0 max-w-[62ch] text-base text-muted md:text-lg">{t("lede")}</p>
          <p className="m-0 max-w-[62ch] text-sm text-muted">
            {t("coverage", { companies: companies.length })}
          </p>
          {data.source === "fixtures" ? (
            <p className="m-0 max-w-[62ch] rounded-card border border-caution/30 bg-caution-soft px-4 py-3 text-sm text-ink">
              <strong>{t("fixtureBannerTitle")}</strong> {t("fixtureBannerBody")}
            </p>
          ) : null}
        </section>

        <section className="pb-12">
          <CompanyFinder companies={companies} />
        </section>

        {featured.length ? (
          <section className="border-t border-line py-10">
            <h2 className="lens-serif m-0 text-xl">{t("featured")}</h2>
            <p className="mt-2 mb-5 max-w-[62ch] text-sm text-muted">{t("featuredNote")}</p>
            <ul className="lens-grid m-0 grid list-none grid-cols-1 gap-3 p-0 md:grid-cols-3">
              {featured.map((company) => {
                const snapshot = getSnapshot(company.ticker);
                const relative = snapshot
                  ? percentagePoints(snapshot.performance.relative_total_return)
                  : null;
                return (
                  <li key={company.ticker}>
                    <Link
                      href={`/company/${company.ticker.toLowerCase()}`}
                      className="flex h-full min-w-0 flex-col gap-2 rounded-card border border-line bg-panel p-5 hover:border-line-strong"
                    >
                      <span className="text-[11px] font-extrabold tracking-wide text-accent">
                        {company.ticker}
                      </span>
                      <span className="lens-serif text-lg text-ink">{company.name}</span>
                      <span className="text-xs text-muted">
                        {locale === "zh" ? (company.categoryZh ?? company.category) : company.category}
                      </span>
                      {relative && snapshot ? (
                        <span className="mt-auto text-xs text-muted">
                          {t("featuredRelative", {
                            value: relative,
                            benchmark: snapshot.benchmark,
                            start: snapshot.period.start ?? "",
                            end: snapshot.period.end ?? "",
                          })}
                        </span>
                      ) : null}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </section>
        ) : null}

        <section className="border-t border-line py-10">
          <h2 className="lens-serif m-0 text-xl">{t("evidenceTitle")}</h2>
          <p className="mt-2 mb-5 max-w-[62ch] text-sm text-muted">{t("evidenceNote")}</p>
          <ul className="lens-grid m-0 grid list-none grid-cols-1 gap-3 p-0 md:grid-cols-3">
            {evidence.map((item) => (
              <li
                key={item.key}
                className="flex min-w-0 flex-col gap-2 rounded-card border border-line bg-panel-muted p-5"
              >
                <h3 className="m-0 text-sm font-bold text-ink">{t(`evidence.${item.key}.title`)}</h3>
                <p className="m-0 text-sm text-muted">{t(`evidence.${item.key}.body`)}</p>
                <Link href={item.href} className="mt-auto text-xs font-bold text-accent">
                  {t("evidenceLink")}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
