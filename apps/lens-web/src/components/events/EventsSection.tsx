"use client";

import { useCallback, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  eventFeed,
  inCoverage,
  publishedVersion,
  resolveView,
  type EventFeed,
  type EventView,
  type PublicEvent,
  type UpcomingEvent,
} from "@/lib/contracts/events";
import { EmptyState } from "@/components/ui/EmptyState";
import { SourceLink } from "@/components/ui/SourceLink";

/**
 * Module E. What happened recently, and what is confirmed next.
 *
 * This replaces a card with five separate layout faults, all of them visible in
 * the screenshot that prompted the rewrite:
 *
 *   - a fixed two-column grid that kept a full-height "what to watch" column
 *     reserved even with nothing confirmed to put in it, so the section was
 *     mostly whitespace;
 *   - grid children without `min-width: 0`, so one long English publisher name
 *     or one unbroken Chinese headline widened a column and pushed the page
 *     sideways;
 *   - one "no events" message standing in for eight different states, so
 *     "this company is not covered" looked the same as "the source failed";
 *   - `manifest_version` printed straight into the page, rendering as
 *     "事件版本 none" when there was no published version;
 *   - heading, status and body at nearly the same weight, so nothing read as
 *     the status.
 *
 * So: the number of columns follows the content, every child may shrink, the
 * eight states each have their own copy, the internal version lives in a
 * technical fold and only when it exists, and the status is a badge.
 *
 * Nothing here invents an event. An absence is always rendered as an absence.
 */
export function EventsSection({ ticker }: { ticker: string }) {
  const t = useTranslations("events");
  const locale = useLocale();
  const chinese = locale === "zh";
  const [feed, setFeed] = useState<EventFeed | null>(null);
  const [view, setView] = useState<EventView>("loading");
  const [attempt, setAttempt] = useState(0);

  /** The published feed, or the reason there is none. Never a partial feed. */
  const read = useCallback(async (): Promise<{ feed: EventFeed | null; view: EventView }> => {
    try {
      const response = await fetch(`/api/events?ticker=${encodeURIComponent(ticker)}`, {
        headers: { Accept: "application/json" },
      });
      const payload: unknown = await response.json();
      const parsed = eventFeed.safeParse(payload);
      if (!parsed.success) return { feed: null, view: "error" };
      return { feed: parsed.data, view: resolveView(parsed.data) };
    } catch {
      return { feed: null, view: "error" };
    }
  }, [ticker]);

  useEffect(() => {
    let current = true;
    void (async () => {
      const result = await read();
      // State is set after the request resolves, and only while this is still
      // the live request: a ticker change mid-flight must not land the previous
      // company's events on this page.
      if (!current) return;
      setFeed(result.feed);
      setView(result.view);
    })();
    return () => {
      current = false;
    };
  }, [read, attempt]);

  const reload = useCallback(() => {
    setFeed(null);
    setView("loading");
    setAttempt((value) => value + 1);
  }, []);

  const version = feed ? publishedVersion(feed) : null;
  const statusLabel = feed?.status_label
    ? ((chinese ? feed.status_label.zh : feed.status_label.en) ?? null)
    : null;
  const tierLabel = feed?.tier_label
    ? ((chinese ? feed.tier_label.zh : feed.tier_label.en) ?? null)
    : null;
  const checked = feed?.checked_at_display
    ? (chinese ? feed.checked_at_display.shanghai : feed.checked_at_display.new_york) ??
      feed.checked_at_display.utc
    : null;

  const upcoming = feed?.upcoming ?? [];
  const events = feed?.events ?? [];
  const showEvents = view === "events" || view === "partial";
  // The layout rule that fixes the screenshot: a second column exists only when
  // there is something confirmed to put in it.
  const twoColumn = showEvents && upcoming.length > 0;

  return (
    <section
      id="events"
      className="scroll-mt-24 rounded-panel border border-line bg-panel p-5 shadow-card md:p-8"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
        <div className="min-w-0">
          <p className="lens-eyebrow m-0 mb-2">{t("eyebrow")}</p>
          <h2 className="lens-serif m-0 text-2xl text-balance md:text-3xl">
            {view === "not_covered" ? t("titleNotCovered") : t("title")}
          </h2>
        </div>
        {view !== "loading" ? (
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <StatusBadge view={view} label={statusLabel} t={t} />
            {tierLabel ? (
              <span className="rounded-full border border-line px-2.5 py-1 text-[11px] text-muted">
                {tierLabel}
              </span>
            ) : null}
          </div>
        ) : null}
      </div>

      {checked ? (
        <p className="mt-3 mb-0 text-xs text-muted">{t("checkedAt", { time: checked })}</p>
      ) : null}

      <div className="mt-6">
        {view === "loading" ? <Skeleton /> : null}

        {view === "not_covered" ? (
          <EmptyState
            title={t("notCovered.title")}
            body={t("notCovered.body", { ticker })}
            footnote={t("notCovered.footnote")}
          />
        ) : null}

        {view === "unavailable" ? (
          <EmptyState
            tone="caution"
            title={t("unavailable.title")}
            body={t("unavailable.body")}
            footnote={t("unavailable.footnote")}
          />
        ) : null}

        {view === "error" ? (
          <div className="flex flex-col items-start gap-3">
            <EmptyState tone="caution" title={t("error.title")} body={t("error.body")} />
            <button
              type="button"
              onClick={reload}
              className="rounded-md border border-line bg-panel px-3 py-1.5 text-xs font-bold text-ink"
            >
              {t("retry")}
            </button>
          </div>
        ) : null}

        {view === "initializing" ? (
          <EmptyState title={t("initializing.title")} body={t("initializing.body")} />
        ) : null}

        {view === "no_new_events" ? (
          <EmptyState
            compact
            title={t("noNew.title")}
            body={t("noNew.body")}
            footnote={
              feed?.coverage_through
                ? t("noNew.footnote", { through: feed.coverage_through })
                : undefined
            }
          />
        ) : null}

        {view === "stale" ? (
          <div className="flex flex-col gap-4">
            <EmptyState
              tone="caution"
              compact
              title={t("stale.title")}
              body={checked ? t("stale.bodyWithTime", { time: checked }) : t("stale.body")}
            />
            {events.length ? <RecentList events={events} chinese={chinese} t={t} /> : null}
          </div>
        ) : null}

        {showEvents ? (
          <div
            className={[
              "lens-grid grid gap-6",
              twoColumn ? "grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]" : "grid-cols-1",
            ].join(" ")}
          >
            <div className="min-w-0">
              <h3 className="m-0 mb-3 text-xs font-bold tracking-wide text-muted uppercase">
                {t("recent")}
              </h3>
              <RecentList events={events} chinese={chinese} t={t} />
            </div>
            {twoColumn ? (
              <div className="min-w-0">
                <h3 className="m-0 mb-3 text-xs font-bold tracking-wide text-muted uppercase">
                  {t("upcoming")}
                </h3>
                <UpcomingList items={upcoming} chinese={chinese} t={t} />
              </div>
            ) : null}
          </div>
        ) : null}

        {/* Nothing confirmed ahead is a one-line statement, not a reserved
            column: an expected date is not a confirmed date and this section
            will not print one as though it were. */}
        {showEvents && upcoming.length === 0 ? (
          <p className="mt-5 mb-0 rounded-card border border-line bg-panel-muted px-4 py-3 text-xs text-muted">
            <strong className="font-bold text-ink">{t("noUpcoming.title")}</strong>{" "}
            {t("noUpcoming.body")}
          </p>
        ) : null}

        {view === "partial" && (feed?.coverage_gaps.length ?? 0) > 0 ? (
          <p className="mt-4 mb-0 text-xs text-muted">
            {t("partialGaps", { count: feed?.coverage_gaps.length ?? 0 })}
          </p>
        ) : null}
      </div>

      <div className="mt-6 flex flex-col gap-2 border-t border-line pt-4 text-xs text-muted">
        <p className="m-0">{t("boundary")}</p>
        {feed && !feed.ai_enabled ? <p className="m-0">{t("askDisabled")}</p> : null}
        {/* The published version is a diagnostic. It appears here, named, and
            only when there is one. */}
        {feed && inCoverage(feed) ? (
          <details>
            <summary className="cursor-pointer font-bold text-accent">{t("technical")}</summary>
            <dl className="mt-2 mb-0 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1">
              <dt>{t("tech.version")}</dt>
              <dd className="m-0 break-all">
                {version ? <code>{version}</code> : t("tech.noVersion")}
              </dd>
              <dt>{t("tech.storage")}</dt>
              <dd className="m-0 break-all">{feed.storage ?? t("tech.unknown")}</dd>
              <dt>{t("tech.status")}</dt>
              <dd className="m-0 break-all">{feed.status ?? t("tech.unknown")}</dd>
            </dl>
          </details>
        ) : null}
      </div>
    </section>
  );
}

type Translator = ReturnType<typeof useTranslations<"events">>;

function StatusBadge({
  view,
  label,
  t,
}: {
  view: EventView;
  label: string | null;
  t: Translator;
}) {
  const tone =
    view === "events"
      ? "bg-positive-soft text-positive border-positive/30"
      : view === "stale" || view === "partial"
        ? "bg-caution-soft text-caution border-caution/30"
        : view === "unavailable" || view === "error"
          ? "bg-critical-soft text-critical border-critical/30"
          : "bg-panel-muted text-muted border-line";
  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-[11px] font-bold tracking-wide uppercase ${tone}`}
    >
      {label ?? t(`view.${view}` as "view.events")}
    </span>
  );
}

function Skeleton() {
  return (
    <div aria-hidden="true" className="flex flex-col gap-2">
      {[0, 1, 2].map((row) => (
        <div
          key={row}
          className="h-16 animate-pulse rounded-card border border-line bg-panel-muted"
        />
      ))}
    </div>
  );
}

function RecentList({
  events,
  chinese,
  t,
}: {
  events: PublicEvent[];
  chinese: boolean;
  t: Translator;
}) {
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0">
      {events.map((event) => {
        const significance = event.significance
          ? ((chinese ? event.significance.zh : event.significance.en) ?? null)
          : null;
        const precision = event.precision_note
          ? ((chinese ? event.precision_note.zh : event.precision_note.en) ?? null)
          : null;
        const when = event.when?.en ?? event.source_published_at ?? null;
        const local = chinese ? event.when?.shanghai : event.when?.new_york;
        return (
          <li
            key={event.id}
            className="flex min-w-0 flex-col gap-1.5 rounded-card border border-line bg-panel-muted p-4"
          >
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[11px] text-muted">
              {when ? <span className="font-bold text-ink">{local || when}</span> : null}
              {event.publisher ? <span className="break-words">{event.publisher}</span> : null}
              {event.title_only ? (
                <span className="rounded bg-paper px-1.5 py-0.5">{t("titleOnly")}</span>
              ) : null}
            </div>
            {/* The headline stays in the language it was published in. A
                translated headline is no longer the source's words. */}
            <p lang={event.title_language ?? "en"} className="m-0 text-sm break-words text-ink">
              {event.title ?? t("untitled")}
            </p>
            {event.excerpt ? (
              <p
                lang={event.title_language ?? "en"}
                className="m-0 text-xs break-words text-muted"
              >
                {event.excerpt}
              </p>
            ) : null}
            {significance ? <p className="m-0 text-xs text-muted">{significance}</p> : null}
            {precision ? <p className="m-0 text-[11px] text-muted italic">{precision}</p> : null}
            {event.source_url ? <SourceLink href={event.source_url}>{t("source")}</SourceLink> : null}
          </li>
        );
      })}
    </ul>
  );
}

function UpcomingList({
  items,
  chinese,
  t,
}: {
  items: UpcomingEvent[];
  chinese: boolean;
  t: Translator;
}) {
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0">
      {items.map((item, index) => {
        const confirmed = item.confirmation === "confirmed";
        const when = chinese ? item.when?.shanghai : item.when?.new_york;
        return (
          <li
            key={item.id ?? `${item.title ?? "upcoming"}-${index}`}
            className="flex min-w-0 flex-col gap-1 rounded-card border border-line bg-panel-muted p-4"
          >
            <span
              className={[
                "w-fit rounded-full px-2 py-0.5 text-[11px] font-bold",
                confirmed ? "bg-positive-soft text-positive" : "bg-caution-soft text-caution",
              ].join(" ")}
            >
              {confirmed ? t("confirmed") : t("expected")}
            </span>
            <p className="m-0 text-sm break-words text-ink">{item.title ?? t("untitled")}</p>
            {/* An expected window is written as a window. Only a confirmed
                item gets a date. */}
            <span className="text-xs text-muted">
              {confirmed
                ? (when ?? item.when?.en ?? t("dateUnknown"))
                : (item.expected_window ?? t("windowUnknown"))}
            </span>
            {item.source_url ? <SourceLink href={item.source_url}>{t("source")}</SourceLink> : null}
          </li>
        );
      })}
    </ul>
  );
}
