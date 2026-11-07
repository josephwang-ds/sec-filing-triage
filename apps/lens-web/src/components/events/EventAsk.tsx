"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { SourceLink } from "@/components/ui/SourceLink";
import type { EventAskDecision, PublicEvent } from "@/lib/contracts/events";

interface Claim {
  text?: string;
  citations?: { id?: string; label?: string | null; url?: string | null }[];
}

interface Answer {
  answer?: Claim[];
  boundaries?: Claim[];
}

const ASK_ERRORS = [
  "event_version_unavailable",
  "event_not_in_version",
  "client_evidence_rejected",
  "ask_not_configured",
  "model_not_available",
  "grounding_validation_failed",
  "provider_failed",
  "question_scope",
  "network",
  "unknown",
] as const;

type AskErrorCode = (typeof ASK_ERRORS)[number];

function askErrorCode(value: string): AskErrorCode {
  return (ASK_ERRORS as readonly string[]).includes(value) ? (value as AskErrorCode) : "unknown";
}

/**
 * One event question, bound to the version on this page.
 *
 * A click never invents a version. If the page has none, or this item is not
 * on that version, the request is not sent and the card says so. The server
 * remains the grounding boundary: this component only forwards the version the
 * reader is looking at, plus the item id.
 */
export function EventAsk({
  ticker,
  event,
  decision,
}: {
  ticker: string;
  event: PublicEvent;
  decision: EventAskDecision;
}) {
  const t = useTranslations("events");
  const locale = useLocale();
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [answer, setAnswer] = useState<Answer | null>(null);

  async function onAsk() {
    setAnswer(null);
    if (decision.state === "missing_version") {
      setNotice(t("missingVersion"));
      return;
    }
    if (decision.state === "version_mismatch") {
      setNotice(t("versionMismatch"));
      return;
    }
    if (decision.state !== "ready") return;

    setPending(true);
    setNotice(null);
    try {
      const configResponse = await fetch("/api/ask", { headers: { Accept: "application/json" } });
      const config = (await configResponse.json()) as { models?: { id?: string }[] };
      const model = config.models?.[0]?.id;
      if (!model) {
        setNotice(t("askError.ask_not_configured"));
        return;
      }
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          ticker,
          provider: model,
          language: locale === "zh" ? "Chinese" : "English",
          depth: "beginner",
          question: t("askQuestion"),
          event_version: decision.version,
          event_id: event.id,
        }),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        const code =
          typeof payload === "object" && payload !== null && "error" in payload
            ? String((payload as { error: unknown }).error)
            : "unknown";
        setNotice(t(`askError.${askErrorCode(code)}`));
        return;
      }
      setAnswer(payload as Answer);
    } catch {
      setNotice(t("askError.network"));
    } finally {
      setPending(false);
    }
  }

  const disabled = decision.state === "disabled" || pending;
  const claims = answer?.answer ?? [];
  const boundaries = answer?.boundaries ?? [];

  return (
    <div className="mt-1 flex min-w-0 flex-col items-start gap-2">
      <button
        type="button"
        disabled={disabled}
        onClick={() => void onAsk()}
        className="max-w-full rounded-md border border-line bg-panel px-3 py-1.5 text-left text-xs font-bold break-words text-ink disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pending ? t("asking") : decision.state === "disabled" ? t("askOff") : t("ask")}
      </button>
      {notice ? (
        <p role="status" className="m-0 text-xs break-words text-caution">
          {notice}
        </p>
      ) : null}
      {answer ? (
        <div role="status" className="flex min-w-0 flex-col gap-2 text-xs break-words text-ink">
          {claims.length === 0 ? <p className="m-0 text-muted">{t("askEmpty")}</p> : null}
          {claims.map((claim, index) => (
            <ClaimLine key={`claim-${index}`} claim={claim} />
          ))}
          {boundaries.length ? (
            <div>
              <p className="m-0 font-bold text-muted">{t("askBoundaries")}</p>
              {boundaries.map((claim, index) => (
                <ClaimLine key={`boundary-${index}`} claim={claim} />
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function ClaimLine({ claim }: { claim: Claim }) {
  return (
    <p className="m-0 break-words">
      {claim.text}
      {(claim.citations ?? []).map((citation) => {
        const label = citation.label || citation.id || "";
        if (!label) return null;
        return citation.url ? (
          <SourceLink key={citation.id ?? citation.url} href={citation.url}>
            {label}
          </SourceLink>
        ) : (
          <span key={citation.id ?? label}> {label}</span>
        );
      })}
    </p>
  );
}
