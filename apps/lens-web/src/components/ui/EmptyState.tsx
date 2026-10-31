import type { ReactNode } from "react";

interface Props {
  title: string;
  body: string;
  /** What the reader can still rely on, when something else on the page covers it. */
  footnote?: ReactNode;
  tone?: "neutral" | "caution";
  compact?: boolean;
}

/**
 * An absence, stated.
 *
 * Compact on purpose: the previous Events card reserved a full two-column
 * block for "nothing here", which read as a broken page rather than as a
 * boundary. Nothing in here is ever a placeholder value -- no invented dates,
 * no sample rows, no internal field names.
 */
export function EmptyState({ title, body, footnote, tone = "neutral", compact = false }: Props) {
  return (
    <div
      className={[
        "rounded-card border",
        tone === "caution"
          ? "border-caution/30 bg-caution-soft"
          : "border-line bg-panel-muted",
        compact ? "px-4 py-3" : "px-5 py-6",
      ].join(" ")}
    >
      <p className="m-0 text-sm font-bold text-ink">{title}</p>
      <p className="mt-1 mb-0 max-w-[65ch] text-sm text-muted">{body}</p>
      {footnote ? <p className="mt-2 mb-0 text-xs text-muted">{footnote}</p> : null}
    </div>
  );
}
