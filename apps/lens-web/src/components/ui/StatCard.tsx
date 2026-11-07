import type { ReactNode } from "react";

interface Props {
  label: string;
  /** Already formatted by the engine's value, or null when the engine has none. */
  value: string | null;
  /** The observation date or period the value belongs to. */
  context?: string | null;
  hint?: string | null;
  missingLabel: string;
  tone?: "neutral" | "positive" | "caution" | "critical";
  children?: ReactNode;
}

const TONES: Record<NonNullable<Props["tone"]>, string> = {
  neutral: "text-ink",
  positive: "text-positive",
  caution: "text-caution",
  critical: "text-critical",
};

/**
 * One measured number with the date it was measured on.
 *
 * A missing value prints the absence rather than a dash that reads as zero,
 * and the context line is not optional decoration: a price without its date
 * and a growth rate without its comparison period are both misreadable.
 */
export function StatCard({
  label,
  value,
  context,
  hint,
  missingLabel,
  tone = "neutral",
  children,
}: Props) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-card border border-line bg-panel-muted p-4">
      <span className="text-[11px] font-bold tracking-wide text-muted uppercase">{label}</span>
      {value === null ? (
        <span className="text-sm text-muted italic">{missingLabel}</span>
      ) : (
        <strong className={`lens-figure text-2xl break-words ${TONES[tone]}`}>{value}</strong>
      )}
      {context ? <span className="text-[11px] text-muted">{context}</span> : null}
      {hint ? <span className="text-[11px] text-muted">{hint}</span> : null}
      {children}
    </div>
  );
}
