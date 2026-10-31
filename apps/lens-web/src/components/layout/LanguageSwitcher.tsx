"use client";

import { useTransition } from "react";
import { useLocale, useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { routing, type Locale } from "@/i18n/routing";

const LABELS: Record<Locale, string> = { zh: "中文", en: "EN" };

/**
 * The language control, and the only place language is switched.
 *
 * It re-navigates to the *same* route in the other locale, dynamic segments
 * and query string included, which is what keeps the reader on AAPL when they
 * press EN instead of dropping them on an English home page. next-intl's router
 * writes the locale cookie as it goes, so a later visit to a bare path and a
 * reload both come back in the language last chosen.
 */
export function LanguageSwitcher() {
  const t = useTranslations("lang");
  const locale = useLocale() as Locale;
  const router = useRouter();
  const pathname = usePathname();
  const [pending, startTransition] = useTransition();

  return (
    <div
      className="flex items-center gap-1 rounded-full border border-line bg-panel p-0.5"
      role="group"
      aria-label={t("label")}
    >
      {routing.locales.map((candidate) => {
        const active = candidate === locale;
        return (
          <button
            key={candidate}
            type="button"
            lang={candidate}
            aria-current={active ? "true" : undefined}
            disabled={pending}
            className={[
              "rounded-full px-2.5 py-1 text-[11px] font-bold transition-colors",
              active ? "bg-ink text-paper" : "text-muted hover:text-ink",
              pending ? "opacity-60" : "",
            ].join(" ")}
            onClick={() => {
              if (active) return;
              startTransition(() => {
                // The same route, in the other language: next-intl's pathname
                // is already locale-stripped, so the reader stays on this
                // company, this tab and this scroll position.
                // Read live rather than through useSearchParams, which would
                // opt this statically generated page out of prerendering for a
                // query string none of these pages depend on.
                const query = typeof window === "undefined" ? "" : window.location.search;
                router.replace(`${pathname}${query}`, { locale: candidate });
              });
            }}
          >
            {LABELS[candidate]}
          </button>
        );
      })}
    </div>
  );
}
