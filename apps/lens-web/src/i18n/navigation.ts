import { createNavigation } from "next-intl/navigation";
import { routing } from "./routing";

/**
 * Locale-aware Link/redirect/router. Using these instead of `next/link` is what
 * keeps the chosen language across navigation: the href stays logical
 * (`/company/aapl`) and the prefix is added for whichever locale is active, so
 * no link has to remember the language and none can drop it.
 */
export const { Link, redirect, usePathname, useRouter, getPathname } = createNavigation(routing);
