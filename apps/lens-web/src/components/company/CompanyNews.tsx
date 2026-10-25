import { getTranslations } from "next-intl/server";
import type { CompanySnapshot, Headline } from "@/lib/contracts/snapshot";
import { Section } from "@/components/ui/Section";
import { EmptyState } from "@/components/ui/EmptyState";
import { SourceLink } from "@/components/ui/SourceLink";
import { isoMinute } from "@/lib/format";

/**
 * Headlines, kept in two lists.
 *
 * Company news and broad market news answer different questions, and a reader
 * has to be able to tell which one a claim came from. Repeating the same
 * general-market rows on every company page as if they were company evidence is
 * exactly the confusion the engine's split prevents, so the split survives here.
 */
export async function CompanyNews({ snapshot }: { snapshot: CompanySnapshot }) {
  const t = await getTranslations("news");
  const scope = snapshot.evidence_scope;
  if (!scope) return null;

  return (
    <Section
      id="context"
      eyebrow={t("eyebrow")}
      title={t("title")}
      intro={t("intro")}
      aside={
        <span className="rounded-full border border-line px-3 py-1 text-[11px] tracking-wide text-muted uppercase">
          {t(`scope.${scope.status}` as "scope.available")}
        </span>
      }
    >
      {snapshot.headlines.length === 0 && snapshot.market_headlines.length === 0 ? (
        <EmptyState compact title={t("empty.title")} body={t("empty.body")} />
      ) : (
        <div className="lens-grid grid grid-cols-1 gap-6 lg:grid-cols-2">
          <HeadlineList
            title={t("companyNews")}
            headlines={snapshot.headlines}
            emptyLabel={t("noCompanyNews")}
          />
          <HeadlineList
            title={t("marketNews")}
            headlines={snapshot.market_headlines}
            emptyLabel={t("noMarketNews")}
          />
        </div>
      )}
      <p className="mt-5 mb-0 text-xs text-muted">
        {scope.generated_at ? t("generated", { time: isoMinute(scope.generated_at) ?? "" }) : null}{" "}
        {t("boundary")}
      </p>
    </Section>
  );
}

function HeadlineList({
  title,
  headlines,
  emptyLabel,
}: {
  title: string;
  headlines: Headline[];
  emptyLabel: string;
}) {
  return (
    <div className="min-w-0">
      <h3 className="m-0 mb-3 text-xs font-bold tracking-wide text-muted uppercase">{title}</h3>
      {headlines.length === 0 ? (
        <p className="m-0 text-xs text-muted italic">{emptyLabel}</p>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {headlines.map((headline) => (
            <li
              key={headline.citation}
              className="flex min-w-0 flex-col gap-1 rounded-card border border-line bg-panel-muted p-4"
            >
              <span className="flex flex-wrap gap-x-3 text-[11px] text-muted">
                <span className="font-bold text-ink">{isoMinute(headline.published_at)}</span>
                <span className="break-words">{headline.publisher}</span>
              </span>
              {/* The headline is the publisher's wording, in the publisher's
                  language. */}
              <p lang="en" className="m-0 text-sm break-words text-ink">
                {headline.headline}
              </p>
              <SourceLink href={headline.url}>{headline.publisher}</SourceLink>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
