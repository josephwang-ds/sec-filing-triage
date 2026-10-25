import { getLocale, getTranslations } from "next-intl/server";
import type { CompanySnapshot } from "@/lib/contracts/snapshot";
import { SourceLink } from "@/components/ui/SourceLink";
import { isoDate, money, signedPercent } from "@/lib/format";

/**
 * Module A. Who this company is, what evidence the page holds about it, and as
 * of when.
 *
 * The price carries its own date in the same breath, because the old hero put a
 * large number under "Latest adjusted close" with the date further down, and a
 * cached close from last Friday read as a live quote. The official name is not
 * translated; the one-line description is, when the engine supplied a Chinese
 * one.
 */
export async function CompanyHero({ snapshot }: { snapshot: CompanySnapshot }) {
  const t = await getTranslations("company");
  const locale = await getLocale();
  const chinese = locale === "zh";
  const profile = snapshot.profile;
  const name = profile.display_name ?? snapshot.company_name;
  const summary = (chinese ? profile.summary_zh : profile.summary) ?? profile.summary;
  const category = (chinese ? profile.category_zh : profile.category) ?? profile.category;
  const close = money(snapshot.market.latest_adjusted_close);
  const priceDate = isoDate(snapshot.market.price_date);
  const coverage = profile.coverage;
  const relative = signedPercent(snapshot.performance.relative_total_return);

  const facts = [
    {
      key: "price",
      label: t("hero.close"),
      value: close,
      context: priceDate ? t("hero.closeOn", { date: priceDate }) : null,
    },
    {
      key: "relative",
      label: t("hero.relative", { benchmark: snapshot.benchmark }),
      value: relative,
      context:
        snapshot.period.start && snapshot.period.end
          ? t("hero.between", { start: snapshot.period.start, end: snapshot.period.end })
          : null,
    },
    {
      key: "filings",
      label: t("hero.filings"),
      value:
        coverage?.filings_in_snapshot === null || coverage?.filings_in_snapshot === undefined
          ? null
          : String(coverage.filings_in_snapshot),
      context: coverage?.price_start
        ? t("hero.priceHistory", { start: coverage.price_start, end: coverage.price_end ?? "" })
        : null,
    },
  ];

  return (
    <section className="flex flex-col gap-6 py-8 md:py-10">
      <div className="flex flex-col gap-3">
        <p className="lens-eyebrow m-0">{t("hero.eyebrow")}</p>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="lens-serif m-0 min-w-0 text-3xl break-words text-balance md:text-5xl">
            {name}
          </h1>
          <span className="rounded-md bg-ink px-2 py-1 text-xs font-extrabold tracking-[0.06em] text-paper">
            {snapshot.ticker}
          </span>
        </div>
        {category ? <p className="m-0 text-sm text-muted">{category}</p> : null}
        {summary ? <p className="m-0 max-w-[68ch] text-base text-muted">{summary}</p> : null}
      </div>

      <dl className="lens-grid m-0 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {facts.map((fact) => (
          <div
            key={fact.key}
            className="flex min-w-0 flex-col gap-1 rounded-card border border-line bg-panel p-4"
          >
            <dt className="text-[11px] font-bold tracking-wide text-muted uppercase">
              {fact.label}
            </dt>
            <dd className="m-0">
              {fact.value === null ? (
                <span className="text-sm text-muted italic">{t("missing")}</span>
              ) : (
                <strong className="lens-figure text-2xl break-words">{fact.value}</strong>
              )}
              {fact.context ? (
                <span className="mt-1 block text-[11px] text-muted">{fact.context}</span>
              ) : null}
            </dd>
          </div>
        ))}
      </dl>

      <p className="m-0 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
        <span>{t("hero.priceField", { field: snapshot.market.price_field ?? "" })}</span>
        {profile.source_url ? (
          <SourceLink href={profile.source_url}>
            {profile.source_label ?? t("hero.secRecord")}
          </SourceLink>
        ) : null}
        {profile.cik ? <span>CIK {profile.cik}</span> : null}
      </p>

      {snapshot.warnings.length ? (
        <ul className="m-0 flex list-none flex-col gap-1 rounded-card border border-caution/30 bg-caution-soft p-4 text-sm text-ink">
          {snapshot.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
