import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { listCompanies } from "@/lib/data/snapshots";

/**
 * The boundary page, kept from the Python site: a company this build holds no
 * evidence about gets a stated absence, not a generated profile.
 */
export default async function NotFound() {
  const t = await getTranslations("notFound");
  const companies = listCompanies();

  return (
    <>
      <SiteHeader />
      <main id="main" className="lens-shell py-16">
        <p className="lens-eyebrow m-0">{t("eyebrow")}</p>
        <h1 className="lens-serif mt-3 mb-0 max-w-[24ch] text-3xl text-balance md:text-5xl">
          {t("title")}
        </h1>
        <p className="mt-4 mb-0 max-w-[62ch] text-base text-muted">
          {t("body", { count: companies.length })}
        </p>
        <p className="mt-6 mb-0">
          <Link href="/" className="font-bold text-accent">
            {t("back")}
          </Link>
        </p>
      </main>
      <SiteFooter />
    </>
  );
}
