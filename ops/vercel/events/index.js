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

function healthFromCheckpoint(checkpoint, nowMs) {
  const sources = [];
  const datasets = (checkpoint && checkpoint.datasets) || {};
  for (const [dataset, body] of Object.entries(datasets)) {
    const states = (body && body.states) || {};
    for (const [ticker, state] of Object.entries(states)) {
      sources.push(sourceLevel(dataset, ticker, state || {}, nowMs));
    }
  }
  const levels = sources.map((source) => source.level);
  let overall = "never_run";
  if (!sources.length) overall = "never_run";
  else if (levels.some((level) => level === "critical")) overall = "critical";
  else if (levels.some((level) => level === "degraded" || level === "partial" || level === "unavailable")) {
    overall = "attention";
  } else if (levels.some((level) => level === "disabled")) overall = "disabled";
  else overall = "current";
  return {
    naive_http_ok: true,
    ok: overall === "current",
    overall,
    sources,
  };
}

function sourceLevel(dataset, ticker, state, nowMs) {
  const last = state.last_successful_check_at ? Date.parse(state.last_successful_check_at) : NaN;
  const cadence = Number(state.cadence_seconds) || 0;
  let missed = null;
  let level = "unavailable";
  if (state.status === "disabled") level = "disabled";
  else if (!Number.isFinite(last) || cadence <= 0) level = "unavailable";
  else {
    missed = Math.floor((nowMs - last) / (cadence * 1000));
    if (missed > 4) level = "critical";
    else if (missed > 2 || state.pending) level = state.pending && missed <= 2 ? "partial" : "degraded";
    else level = state.status === "no_new_events" ? "current" : "current";
  }
  return {
    dataset,
    key: ticker,
    last_successful_check_at: state.last_successful_check_at || null,
    level,
    missed_windows: missed,
    pending: Boolean(state.pending),
    status: state.status || level,
  };
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
