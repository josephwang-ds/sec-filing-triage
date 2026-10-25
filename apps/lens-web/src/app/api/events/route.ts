import { NextResponse, type NextRequest } from "next/server";
import { eventFeed } from "@/lib/contracts/events";

/**
 * The event feed, read-only, from the server.
 *
 * This endpoint never writes. The published feed lives in a private Vercel
 * Blob that one scheduled job owns, and a preview deployment that could write
 * there would be able to corrupt the live feed; so there is no write path here
 * at all, and no blob token is read in this process. When an upstream is
 * configured the request is proxied from the server, which is also what keeps
 * any credential out of the browser bundle.
 *
 * `LENS_EVENTS_UPSTREAM` is the origin that serves the real `/api/events`.
 * Without it this returns the engine's own shape for "no published feed", with
 * the 200 the upstream itself uses for that case -- the status codes carry
 * business meaning and are not re-mapped here.
 */
export const dynamic = "force-dynamic";

const TICKER = /^[A-Z.]{1,6}$/;
const UPSTREAM = (process.env.LENS_EVENTS_UPSTREAM ?? "").replace(/\/+$/, "");

function notConfigured(ticker: string | null) {
  return {
    schema_version: "company-lens.events-public.v1",
    ticker,
    status: "unavailable",
    status_label: { en: "Feed unavailable", zh: "事件源不可用" },
    storage: "not_configured",
    coverage_tier: "unsupported",
    tier_label: { en: "Outside the fetch set", zh: "不在抓取范围" },
    coverage_gaps: [],
    checked_at: null,
    manifest_version: null,
    ai_enabled: false,
    events: [],
    upcoming: [],
    message:
      "No event feed is configured for this deployment. That is not the same as there being no events.",
  };
}

export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const view = url.searchParams.get("view");
  const ticker = (url.searchParams.get("ticker") ?? "").trim().toUpperCase();

  if (view !== "health" && !TICKER.test(ticker)) {
    return NextResponse.json({ error: "ticker_required" }, { status: 400 });
  }

  if (!UPSTREAM) {
    const body =
      view === "health"
        ? { naive_http_ok: true, ok: false, overall: "never_run", sources: [] }
        : notConfigured(ticker || null);
    return NextResponse.json(body, {
      status: 200,
      headers: { "Cache-Control": "no-store", "X-Lens-Events-Source": "not_configured" },
    });
  }

  const target = new URL(`${UPSTREAM}/api/events`);
  if (view === "health") target.searchParams.set("view", "health");
  else target.searchParams.set("ticker", ticker);

  try {
    const upstream = await fetch(target, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    });
    const payload: unknown = await upstream.json();
    // Validated before it reaches the page, so a feed from an older deployment
    // is a stated absence rather than a render-time crash. Unknown fields are
    // preserved; the status code is passed through unchanged.
    const parsed = view === "health" ? null : eventFeed.safeParse(payload);
    return NextResponse.json(parsed && parsed.success ? parsed.data : payload, {
      status: upstream.status,
      headers: { "Cache-Control": "no-store", "X-Lens-Events-Source": "upstream" },
    });
  } catch {
    // The upstream being unreachable is not the same as the company having no
    // events, and the body says which one this is.
    return NextResponse.json(
      { ...notConfigured(ticker || null), storage: "read_error", status: "unavailable" },
      {
        status: 200,
        headers: { "Cache-Control": "no-store", "X-Lens-Events-Source": "read_error" },
      },
    );
  }
}
