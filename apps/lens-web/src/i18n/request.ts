import { getRequestConfig } from "next-intl/server";
import { hasLocale } from "next-intl";
import { routing } from "./routing";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested) ? requested : routing.defaultLocale;
  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
    // Server and client must agree, or the first paint carries one time zone
    // and the hydrated page another. Everything this site shows is a US market
    // date, so that is the zone it is formatted in.
    timeZone: "America/New_York",
    formats: {
      dateTime: {
        day: { year: "numeric", month: "short", day: "numeric" },
      },
    },
  };
});
