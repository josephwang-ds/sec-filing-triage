"use strict";

const fs = require("node:fs");
const path = require("node:path");

const PUBLIC_PREFIX = "lens-events/public";
const BUNDLED = readJson("public.json") || { companies: {}, health: null };

function readJson(name) {
  try {
    return JSON.parse(fs.readFileSync(path.join(__dirname, name), "utf8"));
  } catch (error) {
    return null;
  }
}

async function readBlob(pathname) {
  const token = process.env.BLOB_READ_WRITE_TOKEN || "";
  if (!token) return null;
  try {
    const listed = await fetch(
      "https://vercel.com/api/blob?prefix=" + encodeURIComponent(pathname) + "&limit=1",
      { headers: { authorization: "Bearer " + token, "x-api-version": "12" } },
    );
    if (!listed.ok) return null;
    const payload = await listed.json();
    const url = payload && payload.blobs && payload.blobs[0] && payload.blobs[0].url;
    if (!url) return null;
    const body = await fetch(url, {
      headers: { authorization: "Bearer " + token, "x-api-version": "12" },
    });
    if (!body.ok) return null;
    return await body.json();
  } catch (error) {
    return null;
  }
}

function unavailable(ticker) {
  return {
    ai_enabled: false,
    events: [],
    manifest_version: null,
    message: "The published event feed is unavailable. That is not the same as there being no events.",
    status: "unavailable",
    storage: "unavailable",
    ticker: ticker || null,
    upcoming: [],
  };
}

module.exports = async function handler(request, response) {
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("Content-Type", "application/json; charset=utf-8");
  response.setHeader("X-Content-Type-Options", "nosniff");
  if (request.method !== "GET") {
    response.setHeader("Allow", "GET");
    return send(response, 405, { error: "method_not_allowed" });
  }
  const view = param(request, "view");
  if (view === "health") {
    const live = await readBlob(PUBLIC_PREFIX + "/health.json");
    const health = live || BUNDLED.health || {
      naive_http_ok: true,
      ok: false,
      overall: "unavailable",
      sources: [],
    };
    return send(response, 200, health);
  }
  const ticker = param(request, "ticker").toUpperCase();
  if (!/^[A-Z.]{1,8}$/.test(ticker)) {
    return send(response, 400, { error: "ticker_required" });
  }
  const live = await readBlob(PUBLIC_PREFIX + "/" + ticker + ".json");
  if (live && live.ticker === ticker) {
    live.storage = "blob";
    return send(response, 200, live);
  }
  const bundled = BUNDLED.companies && BUNDLED.companies[ticker];
  if (bundled) {
    return send(response, 200, { ...bundled, storage: bundled.storage || "build_snapshot" });
  }
  return send(response, 200, unavailable(ticker));
};

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
