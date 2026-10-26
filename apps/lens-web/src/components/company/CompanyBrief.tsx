import { getLocale, getTranslations } from "next-intl/server";
import type { Claim, CompanySnapshot } from "@/lib/contracts/snapshot";

const SLOTS = ["what_changed", "why_it_matters", "uncertainties"] as const;

/**
 * The three-part brief the engine writes for every snapshot: what the latest
 * filing is, what the history shows, and what this evidence cannot settle.
 *
 * The labels say which kind of statement each one is -- observed, calculated,
 * interpreted -- because the third card is the one a reader is most likely to
 * mistake for a finding. Chinese text is the engine's own `text_zh`; where it
 * did not supply one the English stands, marked as English, rather than being
 * machine-translated here.
 */
export async function CompanyBrief({ snapshot }: { snapshot: CompanySnapshot }) {
  const t = await getTranslations("brief");
  const locale = await getLocale();
  const chinese = locale === "zh";
  const explanation = snapshot.explanation;

  const cards = SLOTS.map((slot) => ({
    slot,
    claims: (explanation[slot] ?? []) as Claim[],
  })).filter((card) => card.claims.length > 0);

  if (cards.length === 0) return null;

  return (
    <section
      id="brief"
      className="scroll-mt-24 rounded-panel border border-ink bg-ink p-5 text-paper shadow-float md:p-8"
    >
      <p className="m-0 mb-2 text-[11px] font-extrabold tracking-[0.13em] text-paper/70 uppercase">
        {t("eyebrow")}
      </p>
      <h2 className="lens-serif m-0 text-2xl text-balance md:text-3xl">{t("title")}</h2>
      <p className="mt-3 mb-0 max-w-[70ch] text-sm text-paper/70">{t("intro")}</p>

      <div className="lens-grid mt-6 grid grid-cols-1 gap-px overflow-hidden rounded-card bg-paper/20 md:grid-cols-3">
        {cards.map((card) => (
          <article key={card.slot} className="min-w-0 bg-ink p-5">
            <span className="text-[11px] font-extrabold tracking-[0.1em] text-paper/60 uppercase">
              {t(`slot.${card.slot}` as "slot.what_changed")}
            </span>
            {card.claims.map((claim, index) => {
              const zh = claim.text_zh ?? null;
              const text = chinese ? (zh ?? claim.text) : claim.text;
              const untranslated = chinese && !zh;
              return (
                <p
                  key={`${card.slot}-${index}`}
                  lang={untranslated ? "en" : undefined}
                  className="lens-serif mt-2 mb-0 text-base break-words text-paper"
                >
                  {text}
                  {untranslated ? (
                    <span className="mt-1 block text-[11px] text-paper/70">{t("sourceLanguage")}</span>
                  ) : null}
                </p>
              );
            })}
          </article>
        ))}
      </div>

      <p className="mt-4 mb-0 text-[11px] text-paper/60">
        {t("mode", { mode: explanation.mode ?? "deterministic_fallback" })} · {t("boundary")}
      </p>
    </section>
  );
}
