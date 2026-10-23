"use strict";

const fs = require("node:fs");
const path = require("node:path");

const BLOB_API = "https://vercel.com/api/blob";
const POINTER_PATH = "lens-events/public/manifest.json";
const CHECKPOINT_PATH = "lens-events/checkpoint.json";
const BUNDLED = readJson("public.json") || { companies: {}, health: null };

function readJson(name) {
  try {
    return JSON.parse(fs.readFileSync(path.join(__dirname, name), "utf8"));
  } catch (error) {
    return null;
  }
}

function blobHeaders() {
  return {
    authorization: "Bearer " + (process.env.BLOB_READ_WRITE_TOKEN || ""),
    "x-api-version": "12",
  };
}

async function readExact(pathname) {
  const token = process.env.BLOB_READ_WRITE_TOKEN || "";
  if (!token) return { configured: false };
  try {
    const listed = await fetch(
      BLOB_API + "?prefix=" + encodeURIComponent(pathname) + "&limit=5",
      { headers: blobHeaders() },
    );
    if (!listed.ok) return { configured: true, error: true };
    const payload = await listed.json();
    const match = ((payload && payload.blobs) || []).find((item) => item.pathname === pathname);
    if (!match || !match.url) return { configured: true, missing: true };
    const body = await fetch(match.url, { headers: blobHeaders() });
    if (!body.ok) return { configured: true, error: true };
    return { configured: true, body: await body.json() };
  } catch (error) {
    return { configured: true, error: true };
  }
}

async function readPointerFeed(ticker) {
  const pointer = await readExact(POINTER_PATH);
  if (!pointer.configured || pointer.error || pointer.missing || !pointer.body) return pointer;
  const entry = pointer.body.tickers && pointer.body.tickers[ticker];
  if (!entry || !entry.feed_url || !entry.version_id) return { configured: true, missing: true };
  try {
    const body = await fetch(entry.feed_url, { headers: blobHeaders() });
    if (!body.ok) return { configured: true, error: true };
    const feed = await body.json();
    if (!feed || feed.manifest_version !== entry.version_id) return { configured: true, missing: true };
    feed.storage = "blob";
    return { configured: true, feed };
  } catch (error) {
    return { configured: true, error: true };
  }
}

const HIGH_FREQUENCY = [
  "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "JPM", "V",
  "UNH", "XOM", "LLY", "JNJ", "MA", "COST", "HD", "PG", "BAC", "WMT",
];

function nyParts(ms) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hourCycle: "h23",
    weekday: "short",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(new Date(ms));
  const value = (type) => {
    const found = parts.find((part) => part.type === type);
    return found ? found.value : "";
  };
  let hour = Number(value("hour"));
  if (hour === 24) hour = 0;
  return {
    year: Number(value("year")),
    month: Number(value("month")),
    day: Number(value("day")),
    hour,
    minute: Number(value("minute")),
    second: Number(value("second")),
    weekday: { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 }[value("weekday")],
  };
}

function utcForNy(year, month, day, hour, minute) {
  let guess = Date.UTC(year, month - 1, day, hour + 5, minute, 0);
  for (let step = 0; step < 6; step += 1) {
    const parts = nyParts(guess);
    const wanted = Date.UTC(year, month - 1, day, hour, minute, 0);
    const seen = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, parts.second);
    if (seen === wanted) return guess;
    guess += wanted - seen;
  }
  return guess;
}

function civilAdd(year, month, day, delta) {
  const next = new Date(Date.UTC(year, month - 1, day));
  next.setUTCDate(next.getUTCDate() + delta);
  return { year: next.getUTCFullYear(), month: next.getUTCMonth() + 1, day: next.getUTCDate() };
}

function nextClock(afterMs, clocks) {
  const local = nyParts(afterMs);
  for (const clock of clocks) {
    const candidate = utcForNy(local.year, local.month, local.day, clock[0], clock[1]);
    if (candidate > afterMs) return candidate;
  }
  const tomorrow = civilAdd(local.year, local.month, local.day, 1);
  return utcForNy(tomorrow.year, tomorrow.month, tomorrow.day, clocks[0][0], clocks[0][1]);
}

function pythonWeekday(year, month, day) {
  return (new Date(Date.UTC(year, month - 1, day)).getUTCDay() + 6) % 7;
}

function nthWeekday(year, month, weekday, n) {
  const offset = (weekday - pythonWeekday(year, month, 1) + 7) % 7;
  return { year, month, day: 1 + offset + 7 * (n - 1) };
}

function lastWeekday(year, month, weekday) {
  const probe = month === 12
    ? new Date(Date.UTC(year + 1, 0, 1) - 86400000)
    : new Date(Date.UTC(year, month, 1) - 86400000);
  const py = (probe.getUTCDay() + 6) % 7;
  return {
    year: probe.getUTCFullYear(),
    month: probe.getUTCMonth() + 1,
    day: probe.getUTCDate() - ((py - weekday + 7) % 7),
  };
}

function observedHoliday(year, month, day) {
  const py = pythonWeekday(year, month, day);
  if (py === 5) return civilAdd(year, month, day, -1);
  if (py === 6) return civilAdd(year, month, day, 1);
  return { year, month, day };
}

function easterSunday(year) {
  const century = Math.floor(year / 100);
  const yearMod = year % 100;
  const epactCentury = Math.floor(century / 4);
  const centuryMod = century % 4;
  const lunarCorrection = Math.floor((century + 8) / 25);
  const centuryAdjustment = Math.floor((century - lunarCorrection + 1) / 3);
  const epact = (19 * (year % 19) + century - epactCentury - centuryAdjustment + 15) % 30;
  const weekdayCentury = Math.floor(yearMod / 4);
  const weekdayYear = yearMod % 4;
  const weekday = (32 + 2 * centuryMod + 2 * weekdayCentury - epact - weekdayYear) % 7;
  const correction = Math.floor((year % 19 + 11 * epact + 22 * weekday) / 451);
  const monthIndex = Math.floor((epact + weekday - 7 * correction + 114) / 31);
  const dayIndex = (epact + weekday - 7 * correction + 114) % 31;
  return { year, month: monthIndex, day: dayIndex + 1 };
}

const holidayCache = new Map();

function fullHolidayKeys(year) {
  if (holidayCache.has(year)) return holidayCache.get(year);
  const easter = easterSunday(year);
  const days = [
    observedHoliday(year, 1, 1),
    nthWeekday(year, 1, 0, 3),
    nthWeekday(year, 2, 0, 3),
    civilAdd(easter.year, easter.month, easter.day, -2),
    lastWeekday(year, 5, 0),
    observedHoliday(year, 6, 19),
    observedHoliday(year, 7, 4),
    nthWeekday(year, 9, 0, 1),
    nthWeekday(year, 11, 3, 4),
    observedHoliday(year, 12, 25),
  ];
  const keys = new Set(days.map((day) => day.year + "-" + day.month + "-" + day.day));
  holidayCache.set(year, keys);
  return keys;
}

function marketPhase(ms) {
  const local = nyParts(ms);
  if (local.weekday >= 5) return "weekend";
  if (fullHolidayKeys(local.year).has(local.year + "-" + local.month + "-" + local.day)) return "holiday";
  const minutes = local.hour * 60 + local.minute;
  if (minutes >= 4 * 60 && minutes < 20 * 60) return "active";
  return "inactive";
}

function intervalMs(dataset, tier, ms, quotaDegraded) {
  if (dataset === "health") return 15 * 60 * 1000;
  const phase = marketPhase(ms);
  if (dataset === "news") {
    if (quotaDegraded || tier !== "high_frequency") return null;
    if (phase === "active") return 30 * 60 * 1000;
    if (phase === "weekend") return 4 * 60 * 60 * 1000;
    return 2 * 60 * 60 * 1000;
  }
  if (dataset === "sec_index") {
    if (tier !== "high_frequency") return null;
    if (phase === "active") return 2 * 60 * 60 * 1000;
    return 6 * 60 * 60 * 1000;
  }
  return null;
}

function nextCheckMs(dataset, tier, afterMs, quotaDegraded) {
  if (dataset === "company_facts") return nextClock(afterMs, [[6, 30]]);
  if (dataset === "full_recompute") return nextClock(afterMs, [[7, 0]]);
  if (dataset === "future_events") return nextClock(afterMs, [[6, 0]]);
  if (dataset === "filing_parse") return afterMs + 30 * 60 * 1000;
  const step = intervalMs(dataset, tier, afterMs, quotaDegraded);
  if (step == null) return nextClock(afterMs, [[8, 0], [18, 0]]);
  return afterMs + step;
}

function missedWindows(dataset, tier, lastMs, nowMs, quotaDegraded) {
  if (!Number.isFinite(lastMs)) return null;
  let cursor = lastMs;
  let missed = 0;
  while (missed < 1000) {
    const due = nextCheckMs(dataset, tier, cursor, quotaDegraded);
    if (due > nowMs) break;
    missed += 1;
    cursor = due;
  }
  return missed;
}

function freshness(missed, failed, disabled) {
  if (disabled) return "disabled";
  if (missed == null) return "unavailable";
  if (missed > 4) return "critical";
  if (missed > 2 || failed) return missed > 2 ? "degraded" : "stale";
  return "current";
}

function tierFor(ticker, wanted) {
  const symbol = String(ticker || "").toUpperCase();
  if (!wanted.includes(symbol)) return "unsupported";
  if (HIGH_FREQUENCY.includes(symbol)) return "high_frequency";
  return "ordinary";
}

function expectedTickers(expected) {
  const source = expected && expected.length ? expected : HIGH_FREQUENCY;
  return source.map((ticker) => String(ticker).toUpperCase());
}

function sourceLevel(dataset, ticker, state, nowMs, tier) {
  const record = state || { key: ticker };
  const last = record.last_successful_check_at ? Date.parse(record.last_successful_check_at) : NaN;
  const missed = missedWindows(dataset, tier, last, nowMs, Boolean(record.quota_degraded));
  const failed = Boolean(record.last_error_class) || record.status === "stale";
  let level = freshness(missed, failed, false);
  const gaps = Array.isArray(record.coverage_gaps) && record.coverage_gaps.length > 0;
  if (level === "current" && (record.pending || gaps || record.status === "partial")) level = "partial";
  return {
    dataset,
    key: record.key || ticker,
    last_attempt_at: record.last_attempt_at || null,
    last_error_class: record.last_error_class || null,
    last_successful_check_at: record.last_successful_check_at || null,
    level,
    missed_windows: missed,
    pending: Boolean(record.pending),
    status: record.status || level,
    tier,
  };
}

function healthFromCheckpoint(checkpoint, nowMs, expected) {
  const wanted = expectedTickers(expected);
  const datasets = (checkpoint && checkpoint.datasets) || {};
  const names = ["news", "sec_index"];
  for (const name of Object.keys(datasets)) {
    if (!names.includes(name)) names.push(name);
  }
  const sources = [];
  for (const dataset of names) {
    const states = (datasets[dataset] && datasets[dataset].states) || {};
    const keys = new Set(Object.keys(states));
    if (dataset === "news" || dataset === "sec_index") {
      for (const ticker of wanted) keys.add(ticker);
    }
    for (const ticker of [...keys].sort()) {
      sources.push(sourceLevel(dataset, ticker, states[ticker] || null, nowMs, tierFor(ticker, wanted)));
    }
  }
  const levels = sources.map((source) => source.level);
  let overall = "unavailable";
  if (!sources.length) overall = "unavailable";
  else if (levels.some((level) => level === "critical")) overall = "critical";
  else if (levels.some((level) => ["degraded", "stale", "partial", "unavailable"].includes(level))) {
    overall = "attention";
  } else if (levels.some((level) => level === "disabled")) overall = "disabled";
  else overall = "current";
  return { naive_http_ok: true, ok: overall === "current", overall, sources };
}

function unavailable(ticker, status) {
  return {
    ai_enabled: false,
    events: [],
    manifest_version: null,
    message: "The published event feed is unavailable. That is not the same as there being no events.",
    status: status || "unavailable",
    storage: status === "read_error" ? "read_error" : "unavailable",
    ticker: ticker || null,
    upcoming: [],
  };
}

async function handler(request, response) {
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("Content-Type", "application/json; charset=utf-8");
  response.setHeader("X-Content-Type-Options", "nosniff");
  if (request.method !== "GET") {
    response.setHeader("Allow", "GET");
    return send(response, 405, { error: "method_not_allowed" });
  }
  const view = param(request, "view");
  if (view === "health") {
    const checkpoint = await readExact(CHECKPOINT_PATH);
    if (!checkpoint.configured) {
      const health = BUNDLED.health || { naive_http_ok: true, ok: false, overall: "not_configured", sources: [] };
      return send(response, 200, health);
    }
    if (checkpoint.error) {
      return send(response, 200, { naive_http_ok: true, ok: false, overall: "read_error", sources: [] });
    }
    if (checkpoint.missing || !checkpoint.body) {
      return send(response, 200, { naive_http_ok: true, ok: false, overall: "never_run", sources: [] });
    }
    return send(response, 200, healthFromCheckpoint(checkpoint.body, Date.now()));
  }
  const ticker = param(request, "ticker").toUpperCase();
  if (!/^[A-Z.]{1,8}$/.test(ticker)) {
    return send(response, 400, { error: "ticker_required" });
  }
  const live = await readPointerFeed(ticker);
  if (live.configured && live.error) return send(response, 200, unavailable(ticker, "read_error"));
  if (live.configured && live.feed) return send(response, 200, live.feed);
  if (live.configured) return send(response, 200, unavailable(ticker, "unavailable"));
  const bundled = BUNDLED.companies && BUNDLED.companies[ticker];
  if (bundled) return send(response, 200, { ...bundled, storage: bundled.storage || "build_snapshot" });
  return send(response, 200, unavailable(ticker, "unavailable"));
}

function param(request, name) {
  if (request.query && request.query[name]) return String(request.query[name]).trim();
  const raw = String(request.url || "");
  const query = raw.includes("?") ? raw.slice(raw.indexOf("?") + 1) : "";
  return new URLSearchParams(query).get(name) || "";
}

function send(response, status, payload) {
  response.statusCode = status;
  response.end(JSON.stringify(payload));
}

handler.healthFromCheckpoint = healthFromCheckpoint;
handler.readPointerFeed = readPointerFeed;
module.exports = handler;
