"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { SourceLink } from "@/components/ui/SourceLink";
import { EmptyState } from "@/components/ui/EmptyState";

interface Model {
  id: string;
  provider: string;
  model: string;
}

interface Scope {
  id: string;
  label: string;
  label_zh?: string | null;
  description?: string | null;
  description_zh?: string | null;
}

interface Config {
  models: Model[];
  scopes: Scope[];
  default_scope: string;
  limits: { max_question_characters?: number; requests_per_hour?: number; configured?: boolean };
  reason?: string | null;
}

interface Claim {
  text: string;
  citations: { id: string; label?: string | null; url?: string | null; section?: string | null }[];
}

interface Answer {
  answer: Claim[];
  boundaries: Claim[];
  meta: {
    provider?: string;
    model?: string;
    evidence_scope?: string;
    evidence_scope_label?: string;
    answered_at?: string;
    evidence_as_of?: string;
    latency_ms?: number;
  };
}

/**
 * Module F. Questions answered from one company's evidence packet, or not at
 * all.
 *
 * The rules live on the server: which evidence a scope exposes, which citation
 * IDs and number literals an answer may use, and the refusal when a question
 * asks for a price call. This component's job is to never imply otherwise. It
 * does not retry a rejected answer as an unvalidated one, it does not fill a
 * failed request with a plausible paragraph, and it says which model and which
 * scope produced what is on screen.
 *
 * Answer text comes back in the language it was generated in. Asking again in
 * the other language generates a new answer; this component will not relabel an
 * English answer as a Chinese one, so the note under a mismatched answer says
 * what it is.
 */
export function AskSection({ ticker, evidenceAsOf }: { ticker: string; evidenceAsOf: string }) {
  const t = useTranslations("ask");
  const locale = useLocale();
  const chinese = locale === "zh";

  const [config, setConfig] = useState<Config | null>(null);
  const [configState, setConfigState] = useState<"loading" | "ready" | "error">("loading");
  const [question, setQuestion] = useState("");
  const [scope, setScope] = useState("");
  const [model, setModel] = useState("");
  const [depth, setDepth] = useState<"beginner" | "professional">("beginner");
  const [answerLanguage, setAnswerLanguage] = useState<"Chinese" | "English">(
    chinese ? "Chinese" : "English",
  );
  const [pending, setPending] = useState(false);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stopped, setStopped] = useState(false);
  const controller = useRef<AbortController | null>(null);

  const limit = config?.limits.max_question_characters ?? 280;

  const [configAttempt, setConfigAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    void (async () => {
      try {
        const response = await fetch("/api/ask", { headers: { Accept: "application/json" } });
        const payload = (await response.json()) as Config;
        if (!current) return;
        setConfig(payload);
        setScope(payload.default_scope ?? "core");
        setModel(payload.models?.[0]?.id ?? "");
        setConfigState("ready");
      } catch {
        if (current) setConfigState("error");
      }
    })();
    return () => {
      current = false;
    };
  }, [configAttempt]);

  const reloadConfig = useCallback(() => {
    setConfig(null);
    setConfigState("loading");
    setError(null);
    setAnswer(null);
    setConfigAttempt((value) => value + 1);
  }, []);

  const suggestions = useMemo(
    () => [t("suggest.latest"), t("suggest.history"), t("suggest.risk")],
    [t],
  );

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!model || pending) return;
    setPending(true);
    setError(null);
    setAnswer(null);
    setStopped(false);
    const abort = new AbortController();
    controller.current = abort;
    try {
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        signal: abort.signal,
        body: JSON.stringify({
          ticker,
          provider: model,
          question: question.trim(),
          language: answerLanguage,
          depth,
          scope,
        }),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        const code =
          typeof payload === "object" && payload !== null && "error" in payload
            ? String((payload as { error: unknown }).error)
            : "unknown";
        setError(code);
        return;
      }
      setAnswer(payload as Answer);
    } catch (caught) {
      if ((caught as Error).name === "AbortError") setStopped(true);
      else setError("network");
    } finally {
      setPending(false);
      controller.current = null;
    }
  }

  const configured = (config?.models.length ?? 0) > 0;
  const activeScope = config?.scopes.find((entry) => entry.id === scope);
  const answeredLanguage = answerLanguage === "Chinese" ? "zh" : "en";
  const mismatch = answer !== null && answeredLanguage !== locale;

  return (
    <section
      id="ask"
      className="scroll-mt-24 border-t border-line py-10 md:py-12"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
        <div className="min-w-0">
          <p className="lens-eyebrow m-0 mb-2">{t("eyebrow")}</p>
          <h2 className="lens-serif m-0 text-2xl text-balance md:text-3xl">{t("title")}</h2>
        </div>
        {configured ? (
          <span className="shrink-0 rounded-full border border-positive/30 px-2.5 py-1 text-[11px] font-bold tracking-wide text-positive uppercase">
            {t("validated")}
          </span>
        ) : null}
      </div>
      <p className="mt-3 mb-6 max-w-[70ch] text-sm text-muted">{t("intro")}</p>

      {configState === "error" ? (
        <EmptyState tone="caution" title={t("configError.title")} body={t("configError.body")} />
      ) : null}

      {configState === "ready" && !configured ? (
        <EmptyState
          title={t("unconfigured.title")}
          body={t("unconfigured.body")}
          footnote={t("unconfigured.footnote")}
        />
      ) : null}

      {configState === "ready" && configured ? (
        <div className="lens-grid grid grid-cols-1 gap-0 overflow-hidden rounded-panel border border-line lg:grid-cols-[minmax(0,5fr)_minmax(0,4fr)]">
          <form onSubmit={submit} className="min-w-0 border-line bg-panel p-5 lg:border-r">
            <div className="flex flex-col gap-3">
              <label className="flex flex-col gap-1.5">
                <span className="text-[11px] font-bold tracking-wide text-muted uppercase">
                  {t("field.question")}
                </span>
                <textarea
                  value={question}
                  onChange={(event) => setQuestion(event.target.value.slice(0, limit))}
                  maxLength={limit}
                  rows={3}
                  placeholder={t("field.questionPlaceholder", { ticker })}
                  className="w-full resize-y rounded-md border border-line bg-panel px-3 py-2 text-sm"
                />
                <span className="text-[11px] text-muted">
                  {t("field.counter", { used: question.trim().length, limit })}
                </span>
              </label>

              <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
                {suggestions.map((suggestion) => (
                  <li key={suggestion}>
                    <button
                      type="button"
                      onClick={() => setQuestion(suggestion.slice(0, limit))}
                      className="rounded-full border border-line px-2.5 py-1 text-[11px] text-accent hover:bg-accent-soft"
                    >
                      {suggestion}
                    </button>
                  </li>
                ))}
              </ul>

              <details className="rounded-md border border-line bg-panel-muted p-3">
                <summary className="cursor-pointer text-xs font-bold text-accent">
                  {t("advanced")}
                </summary>
                <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <label className="flex min-w-0 flex-col gap-1.5">
                    <span className="text-[11px] font-bold tracking-wide text-muted uppercase">
                      {t("field.scope")}
                    </span>
                    <select
                      value={scope}
                      onChange={(event) => setScope(event.target.value)}
                      className="h-10 w-full rounded-md border border-line bg-panel px-2 text-sm"
                    >
                      {config?.scopes.map((entry) => (
                        <option key={entry.id} value={entry.id}>
                          {(chinese ? entry.label_zh : entry.label) ?? entry.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex min-w-0 flex-col gap-1.5">
                    <span className="text-[11px] font-bold tracking-wide text-muted uppercase">
                      {t("field.model")}
                    </span>
                    <select
                      value={model}
                      onChange={(event) => setModel(event.target.value)}
                      className="h-10 w-full rounded-md border border-line bg-panel px-2 text-sm"
                    >
                      {config?.models.map((entry) => (
                        <option key={entry.id} value={entry.id}>
                          {entry.provider}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="flex min-w-0 flex-col gap-1.5">
                    <span className="text-[11px] font-bold tracking-wide text-muted uppercase">
                      {t("field.answerLanguage")}
                    </span>
                    <select
                      value={answerLanguage}
                      onChange={(event) =>
                        setAnswerLanguage(event.target.value as "Chinese" | "English")
                      }
                      className="h-10 w-full rounded-md border border-line bg-panel px-2 text-sm"
                    >
                      <option value="Chinese">{t("language.chinese")}</option>
                      <option value="English">{t("language.english")}</option>
                    </select>
                  </label>
                  <label className="flex min-w-0 flex-col gap-1.5">
                    <span className="text-[11px] font-bold tracking-wide text-muted uppercase">
                      {t("field.depth")}
                    </span>
                    <select
                      value={depth}
                      onChange={(event) =>
                        setDepth(event.target.value as "beginner" | "professional")
                      }
                      className="h-10 w-full rounded-md border border-line bg-panel px-2 text-sm"
                    >
                      <option value="beginner">{t("depth.beginner")}</option>
                      <option value="professional">{t("depth.professional")}</option>
                    </select>
                  </label>
                </div>
                {activeScope ? (
                  <p className="mt-3 mb-0 text-[11px] text-muted">
                    {(chinese ? activeScope.description_zh : activeScope.description) ??
                      activeScope.description}
                  </p>
                ) : null}
              </details>

              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="submit"
                  disabled={pending || question.trim().length < 4}
                  className="min-w-[120px] rounded-md bg-ink px-4 py-2.5 text-sm font-bold text-paper disabled:opacity-45"
                >
                  {pending ? t("asking") : t("submit")}
                </button>
                {pending ? (
                  <button
                    type="button"
                    onClick={() => controller.current?.abort()}
                    className="rounded-md border border-line px-3 py-2 text-xs font-bold text-ink"
                  >
                    {t("stop")}
                  </button>
                ) : null}
                <span className="text-[11px] text-muted">
                  {t("rate", { perHour: config?.limits.requests_per_hour ?? 8 })}
                </span>
              </div>
            </div>
          </form>

          <div
            aria-live="polite"
            className="min-h-[320px] min-w-0 bg-panel-muted p-5 text-sm text-muted"
          >
            {pending ? (
              <p className="m-0">{t("reading")}</p>
            ) : stopped ? (
              <p className="m-0">{t("stopped")}</p>
            ) : error ? (
              <div className="flex flex-col items-start gap-3">
                <p className="m-0 font-bold text-critical">
                  {t(`error.${error}` as "error.network")}
                </p>
                <p className="m-0">{t("withheld")}</p>
                <button
                  type="button"
                  onClick={reloadConfig}
                  className="rounded-md border border-line bg-panel px-3 py-1.5 text-xs font-bold text-ink"
                >
                  {t("retry")}
                </button>
              </div>
            ) : answer ? (
              <div className="flex flex-col gap-4">
                <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line pb-3">
                  <span className="text-[11px] font-extrabold tracking-wide text-positive uppercase">
                    {t("validatedAnswer")}
                  </span>
                  <small className="text-[11px]">
                    {t("answerMeta", {
                      model: answer.meta.model ?? "",
                      scope: answer.meta.evidence_scope_label ?? answer.meta.evidence_scope ?? "",
                      asOf: answer.meta.evidence_as_of ?? evidenceAsOf,
                    })}
                  </small>
                </header>
                {answer.answer.map((claim, index) => (
                  <article key={`claim-${index}`} className="min-w-0">
                    <p
                      lang={answeredLanguage}
                      className="lens-serif m-0 text-base break-words text-ink"
                    >
                      {claim.text}
                    </p>
                    {claim.citations.length ? (
                      <ul className="m-0 mt-2 flex list-none flex-wrap gap-2 p-0">
                        {claim.citations.map((citation) => (
                          <li key={citation.id} className="min-w-0">
                            {citation.url ? (
                              <SourceLink href={citation.url}>
                                {citation.label ?? citation.id}
                              </SourceLink>
                            ) : (
                              <span className="text-[11px]">{citation.label ?? citation.id}</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </article>
                ))}
                {answer.boundaries.length ? (
                  <details>
                    <summary className="cursor-pointer text-xs font-bold text-caution">
                      {t("limitations")}
                    </summary>
                    {answer.boundaries.map((claim, index) => (
                      <p
                        key={`boundary-${index}`}
                        lang={answeredLanguage}
                        className="mt-2 mb-0 break-words"
                      >
                        {claim.text}
                      </p>
                    ))}
                  </details>
                ) : null}
                {mismatch ? <p className="m-0 text-[11px]">{t("originalLanguage")}</p> : null}
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                <p className="m-0 text-[11px] font-extrabold tracking-wide text-positive uppercase">
                  {t("howItWorks")}
                </p>
                <ol className="m-0 flex list-none flex-col gap-2 p-0">
                  {["evidence", "citations", "refusal"].map((step, index) => (
                    <li key={step} className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-2">
                      <span className="font-extrabold text-positive">{index + 1}</span>
                      <span>{t(`step.${step}` as "step.evidence")}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        </div>
      ) : null}

      <p className="mt-4 mb-0 text-xs text-muted">{t("boundary")}</p>
    </section>
  );
}
