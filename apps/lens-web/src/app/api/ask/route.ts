import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { NextResponse, type NextRequest } from "next/server";

/**
 * `/api/ask`, served by the production function itself.
 *
 * The handler under `ops/vercel/ask/` is the grounding boundary: it holds the
 * evidence allow-lists, the citation and number-literal validation, the refusal
 * patterns, the per-IP window and the daily spend ceiling. Reimplementing any
 * of that in TypeScript would mean two copies of the rule that keeps an answer
 * tied to its evidence, and the copy that drifts is the one that serves
 * readers. So `scripts/prepare-data.mjs` stages that exact file next to its
 * evidence bundle and this route adapts the Node request/response pair it
 * expects. Request validation, status codes and bodies are therefore the live
 * site's, unchanged.
 *
 * Provider keys are read inside that process, from the environment, and never
 * leave it. With no evidence bundle staged, Ask reports itself unconfigured
 * instead of answering: an answer with no evidence behind it is the one output
 * this feature may not produce.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Handler = (request: AskRequest, response: AskResponse) => Promise<void> | void;

interface AskRequest {
  method: string;
  headers: Record<string, string>;
  body?: unknown;
}

interface AskResponse {
  statusCode: number;
  setHeader(name: string, value: string): void;
  end(body?: string): void;
}

const require = createRequire(import.meta.url);
const askRoot = path.join(process.cwd(), ".lens", "ask");

let cached: Handler | null = null;
let loadError: string | null = null;

function handler(): Handler | null {
  if (cached) return cached;
  if (loadError) return null;
  const entry = path.join(askRoot, "index.cjs");
  const evidence = path.join(askRoot, "evidence.json");
  if (!fs.existsSync(entry) || !fs.existsSync(evidence)) {
    loadError = "evidence_missing";
    return null;
  }
  try {
    // Required at runtime from an absolute path, so the bundler leaves it
    // alone and the module reads its evidence.json from beside itself, exactly
    // as it does on the live site. `outputFileTracingIncludes` ships the pair.
    cached = require(entry) as Handler;
    return cached;
  } catch (error) {
    loadError = error instanceof Error ? error.message : "load_failed";
    return null;
  }
}

function unconfigured(method: string) {
  if (method === "GET") {
    // The same document shape the function's GET returns, with nothing
    // offered: a model list cannot be empty *and* a question be answerable.
    return NextResponse.json(
      {
        schema_version: "company-lens.ask-models.v2",
        models: [],
        scopes: [],
        default_scope: "core",
        limits: { evidence_only: true, configured: false },
        reason: loadError ?? "evidence_missing",
      },
      { status: 200, headers: { "Cache-Control": "no-store" } },
    );
  }
  return NextResponse.json(
    {
      error: "ask_not_configured",
      message:
        "This deployment has no Ask evidence bundle, so no grounded answer can be produced here.",
    },
    { status: 503, headers: { "Cache-Control": "no-store" } },
  );
}

async function invoke(request: NextRequest, body?: unknown) {
  const live = handler();
  if (!live) return unconfigured(request.method);

  const headers: Record<string, string> = {};
  request.headers.forEach((value, key) => {
    headers[key.toLowerCase()] = value;
  });

  const collected: Record<string, string> = {};
  let status = 200;
  let payload = "";
  let settled: (() => void) | null = null;
  const finished = new Promise<void>((resolve) => {
    settled = resolve;
  });

  const response: AskResponse = {
    get statusCode() {
      return status;
    },
    set statusCode(value: number) {
      status = value;
    },
    setHeader(name: string, value: string) {
      collected[name] = value;
    },
    end(chunk?: string) {
      payload = chunk ?? "";
      settled?.();
    },
  };

  await live({ method: request.method, headers, body }, response);
  await finished;

  return new NextResponse(payload, {
    status,
    headers: { ...collected, "Cache-Control": "no-store" },
  });
}

export async function GET(request: NextRequest) {
  return invoke(request);
}

export async function POST(request: NextRequest) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  return invoke(request, body);
}
