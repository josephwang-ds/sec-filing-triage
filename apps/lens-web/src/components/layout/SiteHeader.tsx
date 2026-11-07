import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { LanguageSwitcher } from "./LanguageSwitcher";

interface Props {
  /** Shown beside the brand on a company page, so the symbol is never lost in navigation. */
  symbol?: string;
}

export async function SiteHeader({ symbol }: Props) {
  const t = await getTranslations("nav");
  const links = [
    { href: "/" as const, label: t("find") },
    { href: "/overview" as const, label: t("overview") },
    { href: "/research" as const, label: t("research") },
    { href: "/earnings" as const, label: t("earnings") },
  ];

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-paper/95 backdrop-blur-md">
      <div className="lens-shell flex h-16 items-center gap-3">
        <Link href="/" className="flex shrink-0 items-center gap-2 font-bold text-ink">
          <span
            aria-hidden="true"
            className="grid size-8 place-items-center rounded-[9px] bg-ink text-[11px] tracking-[0.04em] text-paper"
          >
            CL
          </span>
          <span className="hidden sm:inline">Company Lens</span>
        </Link>
        {symbol ? (
          <span className="rounded-md border border-line bg-panel px-2 py-1 text-[11px] font-extrabold tracking-[0.06em] text-ink">
            {symbol}
          </span>
        ) : null}
        <nav aria-label={t("site")} className="ml-auto hidden items-center gap-1 md:flex">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="rounded-md px-2.5 py-1.5 text-xs font-bold text-muted hover:bg-panel hover:text-ink"
            >
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto md:ml-3">
          <LanguageSwitcher />
        </div>
      </div>
      {/* Mobile navigation: a scrollable rail rather than a hamburger, so every
          destination stays one tap away and nothing overlaps at 375px. */}
      <nav
        aria-label={t("site")}
        className="flex gap-1 overflow-x-auto border-t border-line px-4 py-2 md:hidden [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className="shrink-0 rounded-md px-2.5 py-1 text-xs font-bold whitespace-nowrap text-muted"
          >
            {link.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
