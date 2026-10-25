import createMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";

/**
 * Locale negotiation. Next 16 calls this convention `proxy`; it is the same
 * request-time hook the `middleware` file used to be.
 *
 * A bare path (`/`, `/company/aapl`, and every legacy `.html` redirect's
 * target) arrives here and leaves with a locale prefix: the cookie the language
 * switcher wrote, else the browser's Accept-Language, else Chinese.
 */
export default createMiddleware(routing);

export const config = {
  // Everything except API routes, Next internals and static files.
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
