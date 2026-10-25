import { getLocale, getTranslations } from "next-intl/server";
import type { CompanySnapshot, FilingBrief, FilingReaction } from "@/lib/contracts/snapshot";
import { Section } from "@/components/ui/Section";
import { EmptyState } from "@/components/ui/EmptyState";
import { SourceLink } from "@/components/ui/SourceLink";
import { isoDate, isoMinute, percent, signedPercent } from "@/lib/format";

/**
 * Module D. The filings themselves, with the fact and the reading of the fact
 * kept apart.
 *
 * What the filing says is quoted and linked. What the engine measured about it
 * -- a text similarity, a novelty score, a post-filing move -- is labelled as a
 * measurement and never written as the filing's own claim. Original disclosure
 * text is not machine-translated: a Chinese reader gets the item label in
 * Chinese and the quoted sentence in the language it was filed in.
 */
export async function FilingsSection({ snapshot }: { snapshot: CompanySnapshot }) {
  const t = await getTranslations("filings");
  const locale = await getLocale();
  const chinese = locale === "zh";
  const refresh = (snapshot.provenance.filing_refresh ?? {}) as { checked_at?: string };
  const checked = isoDate(refresh.checked_at ?? (snapshot.provenance.written_at as string));

  return (
    <Section
      id="filings"
      eyebrow={t("eyebrow")}
      title={t("title")}
      intro={t("intro")}
      aside={
        checked ? (
          <span className="rounded-full border border-line px-3 py-1 text-[11px] tracking-wide text-muted uppercase">
            {refresh.checked_at ? t("secChecked", { date: checked }) : t("secCollected", { date: checked })}
          </span>
        ) : null
      }
    >
      {snapshot.latest_filings.length === 0 ? (
        <EmptyState title={t("empty.title")} body={t("empty.body")} />
      ) : (
        <div className="flex flex-col gap-2">
          {snapshot.latest_filings.map((filing, index) => (
            <FilingCard
              key={filing.accession}
              filing={filing}
              benchmark={snapshot.benchmark}
              chinese={chinese}
              open={index === 0}
              t={t}
            />
          ))}
        </div>
      )}

      {snapshot.filing_timeline.length ? (
        <div className="mt-6">
          <h3 className="m-0 text-xs font-bold tracking-wide text-muted uppercase">
            {t("timeline")}
          </h3>
          <p className="mt-1 mb-3 max-w-[70ch] text-xs text-muted">{t("timelineNote")}</p>
          <ul className="lens-grid m-0 grid list-none grid-cols-1 gap-2 p-0 sm:grid-cols-2 lg:grid-cols-4">
            {snapshot.filing_timeline.slice(0, 8).map((point) => (
              <li
                key={point.accession}
                className="flex min-w-0 flex-col gap-1 rounded-card border border-line bg-panel-muted p-3"
              >
                <span className="text-[11px] font-bold text-ink">{isoDate(point.accepted_at)}</span>
                <span className="text-xs break-words text-muted">
                  {(chinese ? point.item_label_zh : point.item_label) ?? point.item_label}
                </span>
                {point.reaction ? (
                  <span className="text-[11px] text-muted">
                    {t("timelineMove", {
                      move: signedPercent(point.reaction.benchmark_adjusted_move) ?? "",
                      session: point.reaction.session,
                    })}
                  </span>
                ) : (
                  <span className="text-[11px] text-muted italic">{t("noReaction")}</span>
                )}
                <SourceLink href={point.source_url}>{t("sourceFiling")}</SourceLink>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Section>
  );
}

type Translator = Awaited<ReturnType<typeof getTranslations<"filings">>>;

function FilingCard({
  filing,
  benchmark,
  chinese,
  open,
  t,
}: {
  filing: FilingBrief;
  benchmark: string;
  chinese: boolean;
  open: boolean;
  t: Translator;
}) {
  const items = filing.items
    .map((item) => (chinese ? (item.label_zh ?? item.label) : item.label))
    .filter(Boolean);

  return (
    <details
      open={open}
      className="min-w-0 overflow-hidden rounded-card border border-line bg-panel"
    >
      <summary className="flex cursor-pointer flex-wrap items-center justify-between gap-3 px-4 py-4">
        <span className="flex min-w-0 items-center gap-3">
          <span className="shrink-0 rounded-md bg-positive-soft px-2 py-1 text-xs font-extrabold text-positive">
            {filing.form}
          </span>
          <span className="flex min-w-0 flex-col">
            <strong className="truncate text-sm">{items[0] ?? filing.form}</strong>
            <small className="text-xs text-muted">{isoMinute(filing.accepted_at)}</small>
          </span>
        </span>
        <span className="flex shrink-0 items-center gap-4 text-xs text-muted">
          {filing.reaction ? (
            <span>
              {t("moveBadge", {
                move: signedPercent(filing.reaction.benchmark_adjusted_move) ?? "",
              })}
            </span>
          ) : null}
          <span aria-hidden="true">▾</span>
        </span>
      </summary>

      <div className="flex flex-col gap-4 border-t border-line bg-panel-muted px-4 py-4">
        {items.length ? (
          <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
            {items.map((item) => (
              <li
                key={item}
                className="rounded-md bg-paper px-2 py-1 text-[11px] break-words text-muted"
              >
                {item}
              </li>
            ))}
          </ul>
        ) : null}

        <div className="lens-grid grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_240px]">
          <div className="flex min-w-0 flex-col gap-4">
            {filing.passages.length ? (
              <div>
                <h4 className="m-0 mb-2 text-[11px] font-bold tracking-wide text-muted uppercase">
                  {t("passages")}
                </h4>
                <div className="flex flex-col gap-2">
                  {filing.passages.slice(0, 3).map((passage) => (
                    <blockquote
                      key={passage.anchor}
                      className="m-0 border-l-2 border-accent/40 bg-panel px-4 py-3"
                    >
                      {/* Filed text, in the language it was filed in. */}
                      <p lang="en" className="lens-serif m-0 mb-2 text-sm break-words">
                        {passage.text}
                      </p>
                      <SourceLink href={passage.source_url}>{t("sourcePassage")}</SourceLink>
                    </blockquote>
                  ))}
                </div>
              </div>
            ) : (
              <p className="m-0 text-xs text-muted italic">{t("noPassages")}</p>
            )}

            {filing.key_numbers.length ? (
              <div>
                <h4 className="m-0 mb-2 text-[11px] font-bold tracking-wide text-muted uppercase">
                  {t("keyNumbers")}
                </h4>
                <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
                  {filing.key_numbers.map((number, index) => (
                    <li
                      key={`${number.label ?? "number"}-${index}`}
                      className="rounded-md bg-accent-soft px-2 py-1 text-[11px] font-bold break-words text-accent"
                    >
                      {[number.label, number.value].filter(Boolean).join(" ")}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {filing.comparison ? (
              <div className="rounded-card border border-line bg-panel p-4">
                <h4 className="m-0 mb-1 text-[11px] font-bold tracking-wide text-muted uppercase">
                  {t("comparison")}
                </h4>
                <p className="m-0 text-xs text-muted">
                  {t("comparisonAgainst", {
                    date: isoDate(filing.comparison.prior_accepted_at) ?? "",
                    changed: filing.comparison.counts.changed ?? 0,
                    added: filing.comparison.counts.added ?? 0,
                    removed: filing.comparison.counts.removed ?? 0,
                  })}
                </p>
                {filing.comparison.changes.slice(0, 2).map((change) => (
                  <div key={`${change.kind}-${change.current?.anchor ?? "none"}`} className="mt-3">
                    <p className="m-0 text-[11px] font-bold text-ink">
                      {t(`changeKind.${change.kind}` as "changeKind.changed")}
                      {change.similarity !== null && change.similarity !== undefined
                        ? ` · ${t("textMatch", { value: percent(change.similarity, 0) ?? "" })}`
                        : ""}
                    </p>
                    {change.current ? (
                      <p lang="en" className="m-0 mt-1 text-xs break-words text-muted">
                        {change.current.text}
                      </p>
                    ) : null}
                  </div>
                ))}
                <p className="mt-3 mb-0">
                  <SourceLink href={filing.comparison.prior_source_url}>
                    {t("priorFiling")}
                  </SourceLink>
                </p>
              </div>
            ) : null}
          </div>

          <aside className="flex min-w-0 flex-col gap-3 rounded-card bg-paper p-4 text-[11px] text-muted">
            <span className="font-bold tracking-wide uppercase">{t("measured")}</span>
            {filing.reaction ? <ReactionRows reaction={filing.reaction} benchmark={benchmark} t={t} /> : (
              <span className="italic">{t("noReaction")}</span>
            )}
            {filing.novelty !== null && filing.novelty !== undefined ? (
              <span>{t("novelty", { value: percent(filing.novelty, 0) ?? "" })}</span>
            ) : null}
            <span className="break-all">
              <code>{filing.accession}</code>
            </span>
            <SourceLink href={filing.source_url}>{t("sourceFiling")}</SourceLink>
          </aside>
        </div>
      </div>
    </details>
  );
}

function ReactionRows({
  reaction,
  benchmark,
  t,
}: {
  reaction: FilingReaction;
  benchmark: string;
  t: Translator;
}) {
  return (
    <>
      <span>
        {t("reactionSession", { session: reaction.session })}
      </span>
      <span>
        {t("reactionMove", {
          move: signedPercent(reaction.benchmark_adjusted_move) ?? "",
          benchmark,
        })}
      </span>
      {reaction.magnitude_percentile !== null && reaction.magnitude_percentile !== undefined ? (
        <span>
          {t("reactionPercentile", {
            value: percent(reaction.magnitude_percentile, 0) ?? "",
            sample: reaction.prior_sample_size,
          })}
        </span>
      ) : null}
      <span className="italic">{t("reactionBoundary")}</span>
    </>
  );
}
