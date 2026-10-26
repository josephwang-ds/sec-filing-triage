import { describe, expect, it } from "vitest";
import {
  coverageGapLines,
  eventAskDecision,
  eventFeed,
  inCoverage,
  publishedVersion,
  resolveView,
} from "@/lib/contracts/events";

function feed(overrides: Record<string, unknown> = {}) {
  return eventFeed.parse({
    schema_version: "company-lens.events-public.v1",
    ticker: "AAPL",
    status: "current",
    coverage_tier: "high_frequency",
    storage: "blob",
    manifest_version: "abc123",
    events: [],
    upcoming: [],
    ...overrides,
  });
}

/**
 * The published version, and the bug this guards.
 *
 * The old card printed `manifest_version` straight into the markup, so a feed
 * with no version rendered as "事件版本 none" -- an internal field name and a
 * placeholder shown to a reader as though "none" were a version.
 */
describe("publishedVersion", () => {
  it("treats null, empty and the 'none' placeholder as no version", () => {
    expect(publishedVersion(feed({ manifest_version: null }))).toBeNull();
    expect(publishedVersion(feed({ manifest_version: "" }))).toBeNull();
    expect(publishedVersion(feed({ manifest_version: "none" }))).toBeNull();
    expect(publishedVersion(feed({ manifest_version: "NONE" }))).toBeNull();
    expect(publishedVersion(feed({ manifest_version: "null" }))).toBeNull();
  });

  it("returns a real version unchanged", () => {
    expect(publishedVersion(feed({ manifest_version: "9f2c1d" }))).toBe("9f2c1d");
  });
});

/**
 * One state per situation.
 *
 * The card this replaces showed the same "no events" message for a company
 * outside the fetch set, a source that had failed, and a check that succeeded
 * with nothing new. Those are three different facts about the world.
 */
describe("resolveView", () => {
  it("separates not-covered from unavailable from nothing-new", () => {
    expect(resolveView(feed({ coverage_tier: "unsupported" }))).toBe("not_covered");
    expect(resolveView(feed({ status: "unavailable" }))).toBe("unavailable");
    expect(resolveView(feed({ storage: "read_error" }))).toBe("unavailable");
    expect(resolveView(feed({ status: "current", events: [] }))).toBe("no_new_events");
  });

  it("keeps a stale or overdue feed distinct from a current one", () => {
    expect(resolveView(feed({ status: "stale" }))).toBe("stale");
    expect(resolveView(feed({ status: "degraded" }))).toBe("stale");
    expect(resolveView(feed({ status: "critical" }))).toBe("stale");
  });

  it("reports a first run as a first run, not as an empty feed", () => {
    expect(resolveView(feed({ initialization: true, events: [] }))).toBe("initializing");
  });

  it("shows events when there are events", () => {
    const withEvents = feed({
      events: [{ id: "e1", title: "A headline", source_url: "https://example.invalid/a" }],
    });
    expect(resolveView(withEvents)).toBe("events");
  });

  it("will not call a partial feed with nothing in it 'partial'", () => {
    // Partial coverage and zero items together is an unavailable feed, not a
    // feed with a caveat: there is nothing for the caveat to qualify.
    expect(resolveView(feed({ status: "partial", events: [] }))).toBe("unavailable");
  });

  it("knows which issuers are inside the fetch set", () => {
    expect(inCoverage(feed({ coverage_tier: "high_frequency" }))).toBe(true);
    expect(inCoverage(feed({ coverage_tier: "ordinary" }))).toBe(true);
    expect(inCoverage(feed({ coverage_tier: "unsupported" }))).toBe(false);
  });
});

describe("eventAskDecision", () => {
  const item = {
    id: "evt-1",
    title: "A headline",
    ask_enabled: true,
    manifest_version: "abc123",
  };

  it("sends only the version published on the page", () => {
    expect(eventAskDecision(feed(), item)).toEqual({ state: "ready", version: "abc123" });
  });

  it("refuses to ask when the page has no version", () => {
    expect(eventAskDecision(feed({ manifest_version: null }), item).state).toBe("missing_version");
    expect(eventAskDecision(feed({ manifest_version: "none" }), item).state).toBe("missing_version");
  });

  it("refuses an item that is not on the page version", () => {
    expect(
      eventAskDecision(feed(), { ...item, manifest_version: "other" }).state,
    ).toBe("version_mismatch");
  });

  it("stays off when the feed has not enabled questions for the item", () => {
    expect(eventAskDecision(feed(), { ...item, ask_enabled: false }).state).toBe("disabled");
  });
});

describe("coverageGapLines", () => {
  it("keeps the recorded window and drops gaps with nothing in them", () => {
    const lines = coverageGapLines(
      feed({
        coverage_gaps: [
          { start: "2026-01-01", end: "2026-01-03", reason: "provider_lookback" },
          {},
        ],
      }),
    );
    expect(lines).toEqual(["2026-01-01 → 2026-01-03 (provider_lookback)"]);
  });
});

describe("feed parsing", () => {
  it("accepts a feed carrying fields this front end does not know about", () => {
    const parsed = eventFeed.safeParse({
      ticker: "AAPL",
      status: "current",
      events: [],
      upcoming: [],
      some_future_field: { nested: true },
    });
    expect(parsed.success).toBe(true);
  });

  it("defaults the collections rather than leaving them undefined", () => {
    const parsed = eventFeed.parse({ ticker: "AAPL", status: "current" });
    expect(parsed.events).toEqual([]);
    expect(parsed.upcoming).toEqual([]);
    expect(parsed.coverage_gaps).toEqual([]);
  });
});
