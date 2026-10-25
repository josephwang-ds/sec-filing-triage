import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

/**
 * Legacy compatibility. The Python site published one flat `.html` file per
 * issuer plus three content pages, and those URLs are linked from the README,
 * the main site and whatever else already points at them. They redirect to the
 * unprefixed route so the next-intl middleware can then negotiate the locale --
 * a redirect straight to `/zh/...` would pin every old link to one language.
 */
const legacyRedirects = [
  { source: "/index.html", destination: "/", permanent: true },
  { source: "/overview.html", destination: "/overview", permanent: true },
  { source: "/research.html", destination: "/research", permanent: true },
  { source: "/404.html", destination: "/not-found", permanent: false },
  // Any other `<ticker>.html`. Kept last so the named pages above win, and
  // bounded to the shape of a symbol: 1-6 letters, digits or dots. An unknown
  // one lands on the company route, which answers with the boundary page
  // rather than inventing a company.
  {
    source: "/:ticker([A-Za-z0-9.]{1,6}).html",
    destination: "/company/:ticker",
    permanent: true,
  },
];

const config: NextConfig = {
  reactStrictMode: true,
  // The Ask handler is the production function, loaded at runtime from the
  // repository's own copy rather than reimplemented here. Tracing has to be
  // told about files that are read instead of imported.
  outputFileTracingIncludes: {
    "/api/ask": ["./.lens/ask/**"],
  },
  async redirects() {
    return legacyRedirects;
  },
};

export default withNextIntl(config);
