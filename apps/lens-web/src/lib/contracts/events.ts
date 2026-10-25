/**
 * The published event feed, mirrored from `company_lens.events.public`.
 *
 * Read defensively on purpose. This is the one payload the page fetches at
 * runtime rather than reading from the build, so it can arrive from an older
 * deployment, from a blob the refresh job wrote mid-cycle, or not at all. A
 * field it does not carry becomes an absence the UI can state, never a default
 * that reads as data.
 */
import { z } from "zod";

/** The states the refresh pipeline distinguishes. One UI treatment each. */
export const eventStatus = z.enum([
  "current",
  "no_new_events",
  "partial",
  "stale",
  "degraded",
  "critical",
  "unavailable",
  "disabled",
]);

export type EventStatus = z.infer<typeof eventStatus>;

const bilingual = z.looseObject({ en: z.string().nullish(), zh: z.string().nullish() });

export const eventWhen = z.looseObject({
  en: z.string().nullish(),
  precision: z.string().nullish(),
  new_york: z.string().nullish(),
  shanghai: z.string().nullish(),
});

export const publicEvent = z.looseObject({
  id: z.string(),
  title: z.string().nullish(),
  /** The language the headline was published in. Never machine-translated here. */
  title_language: z.string().nullish(),
  title_only: z.boolean().nullish(),
  excerpt: z.string().nullish(),
  publisher: z.string().nullish(),
  source_kind: z.string().nullish(),
  source_url: z.string().nullish(),
  source_published_at: z.string().nullish(),
  time_precision: z.string().nullish(),
  precision_note: bilingual.nullish(),
  significance: bilingual.nullish(),
  status: z.string().nullish(),
  duplicate_group_id: z.string().nullish(),
  manifest_version: z.string().nullish(),
  ask_enabled: z.boolean().nullish(),
  when: eventWhen.nullish(),
});

export const upcomingEvent = z.looseObject({
  id: z.string().nullish(),
  title: z.string().nullish(),
  /** "confirmed" or "expected". An expected date is never shown as a date on the calendar. */
  confirmation: z.string().nullish(),
  expected_window: z.string().nullish(),
  source_url: z.string().nullish(),
  when: eventWhen.nullish(),
});

export const eventFeed = z.looseObject({
  schema_version: z.string().nullish(),
  ticker: z.string().nullish(),
  status: z.string().nullish(),
  status_label: bilingual.nullish(),
  storage: z.string().nullish(),
  coverage_tier: z.string().nullish(),
  tier_label: bilingual.nullish(),
  coverage_through: z.string().nullish(),
  coverage_gaps: z.array(z.unknown()).default([]),
  checked_at: z.string().nullish(),
  checked_at_display: z
    .looseObject({
      utc: z.string().nullish(),
      new_york: z.string().nullish(),
      shanghai: z.string().nullish(),
    })
    .nullish(),
  initialization: z.boolean().nullish(),
  pending: z.boolean().nullish(),
  quota_degraded: z.boolean().nullish(),
  /** Null, "", or the literal "none" all mean "no published version". */
  manifest_version: z.string().nullish(),
  ai_enabled: z.boolean().nullish(),
  events: z.array(publicEvent).default([]),
  upcoming: z.array(upcomingEvent).default([]),
  message: z.string().nullish(),
});

export type EventFeed = z.infer<typeof eventFeed>;
export type PublicEvent = z.infer<typeof publicEvent>;
export type UpcomingEvent = z.infer<typeof upcomingEvent>;

/**
 * A published version, or nothing.
 *
 * The old card printed `manifest_version` straight into the page, so a feed
 * with no version rendered as "事件版本 none" -- an internal field name and a
 * placeholder, shown to a reader as though "none" were a version. A version is
 * only a version when it is a non-empty string that is not the placeholder.
 */
export function publishedVersion(feed: EventFeed): string | null {
  const raw = (feed.manifest_version ?? "").trim();
  if (!raw || raw.toLowerCase() === "none" || raw.toLowerCase() === "null") return null;
  return raw;
}

/** Whether this issuer is inside the fetch set at all. */
export function inCoverage(feed: EventFeed): boolean {
  return feed.coverage_tier === "high_frequency" || feed.coverage_tier === "ordinary";
}

/**
 * The one state the UI renders, resolved from the several fields that can each
 * imply a different one. Resolved once, here, rather than in the markup, so
 * "unsupported", "temporarily unavailable" and "nothing new" cannot collapse
 * into one grey box.
 */
export type EventView =
  | "loading"
  | "events"
  | "no_new_events"
  | "not_covered"
  | "unavailable"
  | "stale"
  | "partial"
  | "initializing"
  | "error";

export function resolveView(feed: EventFeed): EventView {
  if (!inCoverage(feed)) return "not_covered";
  const status = feed.status ?? "unavailable";
  if (feed.storage === "read_error") return "unavailable";
  if (status === "unavailable" || status === "disabled") return "unavailable";
  if (status === "critical" || status === "degraded") return "stale";
  if (feed.initialization && feed.events.length === 0) return "initializing";
  if (status === "stale") return "stale";
  if (status === "partial") return feed.events.length ? "partial" : "unavailable";
  if (feed.events.length === 0) return "no_new_events";
  return "events";
}
