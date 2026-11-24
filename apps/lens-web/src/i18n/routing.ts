import { defineRouting } from "next-intl/routing";

/**
 * Chinese is the default and it is still prefixed.
 *
 * `as-needed` would leave the default language on bare `/company/aapl` and the
 * other on `/en/company/aapl`, so a shared link would not say which language it
 * was read in and the two pages would not be symmetrical. Both are prefixed,
 * both are addressable, and a bare path is a redirect rather than a page.
 */
export const routing = defineRouting({
  locales: ["zh", "en"],
  defaultLocale: "zh",
  localePrefix: "always",
  localeCookie: {
    name: "LENS_LOCALE",
    maxAge: 60 * 60 * 24 * 365,
    sameSite: "lax",
  },
});

export type Locale = (typeof routing.locales)[number];

export function isLocale(value: string): value is Locale {
  return (routing.locales as readonly string[]).includes(value);
}
