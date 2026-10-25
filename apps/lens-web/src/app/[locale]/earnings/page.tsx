import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { featuredCompanies } from "@/lib/data/snapshots";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "earnings" });
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    alternates: { canonical: `/${locale}/earnings`, languages: { zh: "/zh/earnings", en: "/en/earnings" } },
  };
}

/**
 * The retired estimated-earnings calendar.
 *
 * This page carries what the live site carries today: the calendar of
 * *estimated* reporting dates was withdrawn, and filed results moved onto the
 * company pages. It is kept as a page rather than a redirect because the old
 * URL is linked from elsewhere and a reader arriving on it deserves the reason,
 * and because an estimated date presented as a schedule is the thing that was
 * wrong with it. Nothing here predicts a future reporting date.
 */
export default async function EarningsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("earnings");
  const featured = featuredCompanies();

  return (
    <>
      <SiteHeader />
      <main id="main" className="lens-shell py-12 md:py-16">
        <div className="max-w-[68ch]">
          <p className="lens-eyebrow m-0">{t("eyebrow")}</p>
          <h1 className="lens-serif mt-3 mb-0 text-3xl text-balance md:text-5xl">{t("title")}</h1>
          <p className="mt-4 mb-0 text-base text-muted">{t("body")}</p>
          <p className="mt-3 mb-0 text-base text-muted">{t("why")}</p>
          <p className="mt-3 mb-0 rounded-card border border-line bg-panel-muted px-4 py-3 text-sm text-muted">
            {t("boundary")}
          </p>

          <h2 className="lens-serif mt-8 mb-3 text-xl">{t("whereTitle")}</h2>
          <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
            {featured.map((company) => (
              <li key={company.ticker}>
                <Link
                  href={`/company/${company.ticker.toLowerCase()}#financials`}
                  className="inline-block rounded-md border border-line bg-panel px-3 py-2 text-sm font-bold text-ink"
                >
                  {company.ticker}
                </Link>
              </li>
            ))}
          </ul>
          <p className="mt-6 mb-0">
            <Link href="/" className="font-bold text-accent">
              {t("find")}
            </Link>
          </p>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
