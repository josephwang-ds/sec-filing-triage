"use client";

import { useId, useMemo, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Link, useRouter } from "@/i18n/navigation";
import type { CompanyListing } from "@/lib/data/snapshots";

interface Props {
  companies: CompanyListing[];
  pageSize?: number;
}

function normalise(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9一-鿿]+/g, "");
}

/**
 * Search and directory over the covered companies, sharing one query.
 *
 * The list it searches is the list of snapshots that exist. There is no
 * remote lookup and no guessing: a symbol outside the set produces a stated
 * boundary, never a generated page for a company this site holds no evidence
 * about. Two searches over one page would be able to disagree, so there is one.
 */
export function CompanyFinder({ companies, pageSize = 24 }: Props) {
  const t = useTranslations("home.search");
  const locale = useLocale();
  const router = useRouter();
  const inputId = useId();
  const listId = useId();
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [active, setActive] = useState(-1);
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const trimmed = query.trim();
  const needle = normalise(trimmed);

  const matches = useMemo(() => {
    if (!needle) return [] as CompanyListing[];
    return companies
      .map((company) => {
        const ticker = normalise(company.ticker);
        const name = normalise(company.name);
        if (ticker === needle) return { company, rank: 0 };
        if (ticker.startsWith(needle)) return { company, rank: 1 };
        if (name.startsWith(needle)) return { company, rank: 2 };
        if (name.includes(needle)) return { company, rank: 3 };
        return null;
      })
      .filter((row): row is { company: CompanyListing; rank: number } => row !== null)
      .sort((a, b) => a.rank - b.rank || a.company.ticker.localeCompare(b.company.ticker))
      .map((row) => row.company);
  }, [companies, needle]);

  const filtered = needle ? matches : companies;
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const current = Math.min(page, pages - 1);
  const slice = filtered.slice(current * pageSize, current * pageSize + pageSize);
  const suggestions = matches.slice(0, 8);

  function go(company: CompanyListing) {
    setOpen(false);
    router.push(`/company/${company.ticker.toLowerCase()}`);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!suggestions.length) return;
      setOpen(true);
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((index) => {
        const next = index + step;
        if (next < 0) return suggestions.length - 1;
        if (next >= suggestions.length) return 0;
        return next;
      });
      return;
    }
    if (event.key === "Enter") {
      const picked = suggestions[active] ?? suggestions[0];
      if (picked) {
        event.preventDefault();
        go(picked);
      }
      return;
    }
    if (event.key === "Escape") {
      setOpen(false);
      setActive(-1);
    }
  }

  const exhausted = Boolean(needle) && matches.length === 0;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-2">
        <label htmlFor={inputId} className="text-[11px] font-bold tracking-wide text-muted uppercase">
          {t("label")}
        </label>
        <div className="relative">
          <input
            id={inputId}
            ref={inputRef}
            type="search"
            role="combobox"
            aria-expanded={open && suggestions.length > 0}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={
              open && active >= 0 && suggestions[active]
                ? `${listId}-${suggestions[active]!.ticker}`
                : undefined
            }
            autoComplete="off"
            spellCheck={false}
            placeholder={t("placeholder")}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(0);
              setActive(-1);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={onKeyDown}
            className="w-full rounded-card border border-line bg-panel px-4 py-3 text-base text-ink placeholder:text-muted"
          />
          {open && suggestions.length > 0 ? (
            <ul
              id={listId}
              role="listbox"
              aria-label={t("results")}
              className="absolute inset-x-0 top-full z-20 mt-1 max-h-72 overflow-y-auto rounded-card border border-line bg-panel shadow-float"
            >
              {suggestions.map((company, index) => (
                <li
                  key={company.ticker}
                  id={`${listId}-${company.ticker}`}
                  role="option"
                  aria-selected={index === active}
                >
                  <button
                    type="button"
                    onMouseEnter={() => setActive(index)}
                    onClick={() => go(company)}
                    className={[
                      "flex w-full items-baseline justify-between gap-3 px-4 py-2.5 text-left",
                      index === active ? "bg-accent-soft" : "",
                    ].join(" ")}
                  >
                    <span className="min-w-0 truncate text-sm text-ink">{company.name}</span>
                    <span className="shrink-0 text-[11px] font-extrabold tracking-wide text-accent">
                      {company.ticker}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        {exhausted ? (
          <p role="status" className="m-0 rounded-card bg-caution-soft px-4 py-3 text-sm text-ink">
            <strong className="font-bold">{t("noMatchTitle", { query: trimmed })}</strong>{" "}
            <span className="text-muted">{t("noMatchBody")}</span>
          </p>
        ) : (
          <p className="m-0 text-xs text-muted">{t("hint", { count: companies.length })}</p>
        )}
        {needle && matches.length > 1 ? (
          <p role="status" className="m-0 text-xs text-muted">
            {t("ambiguous", { count: matches.length })}
          </p>
        ) : null}
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="lens-serif m-0 text-xl">{t("directory")}</h2>
          <p className="m-0 text-xs text-muted">
            {t("showing", {
              from: filtered.length === 0 ? 0 : current * pageSize + 1,
              to: current * pageSize + slice.length,
              total: filtered.length,
            })}
          </p>
        </div>
        <ul className="lens-grid m-0 grid list-none grid-cols-1 gap-2 p-0 sm:grid-cols-2 lg:grid-cols-3">
          {slice.map((company) => (
            <li key={company.ticker}>
              <Link
                href={`/company/${company.ticker.toLowerCase()}`}
                className="flex h-full min-w-0 flex-col gap-1 rounded-card border border-line bg-panel px-4 py-3 hover:border-line-strong"
              >
                <span className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-sm font-bold text-ink">{company.name}</span>
                  <span className="shrink-0 text-[11px] font-extrabold tracking-wide text-accent">
                    {company.ticker}
                  </span>
                </span>
                <span className="text-[11px] text-muted">
                  {locale === "zh" ? (company.categoryZh ?? company.category) : company.category}
                </span>
              </Link>
            </li>
          ))}
        </ul>
        {pages > 1 ? (
          <nav className="flex items-center justify-center gap-2 pt-2" aria-label={t("pagination")}>
            <button
              type="button"
              disabled={current === 0}
              onClick={() => setPage(current - 1)}
              className="rounded-md border border-line px-3 py-1.5 text-xs font-bold text-ink disabled:opacity-40"
            >
              {t("previous")}
            </button>
            <span className="text-xs text-muted">{t("page", { page: current + 1, pages })}</span>
            <button
              type="button"
              disabled={current >= pages - 1}
              onClick={() => setPage(current + 1)}
              className="rounded-md border border-line px-3 py-1.5 text-xs font-bold text-ink disabled:opacity-40"
            >
              {t("next")}
            </button>
          </nav>
        ) : null}
      </div>
    </div>
  );
}
