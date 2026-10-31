import type { ReactNode } from "react";

interface Props {
  id?: string;
  eyebrow?: string;
  title: string;
  intro?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  /** A section whose own frame would compete with the cards inside it. */
  bare?: boolean;
}

/**
 * One section of a page, with one heading level and one place the frame is
 * drawn. Every module uses it, which is what keeps the company page from
 * reading as six separately designed pages stacked up.
 */
export function Section({ id, eyebrow, title, intro, aside, children, bare = false }: Props) {
  return (
    <section
      id={id}
      className={
        bare
          ? "scroll-mt-24 border-t border-line py-10 md:py-12"
          : "scroll-mt-24 rounded-panel border border-line bg-panel p-5 shadow-card md:p-8"
      }
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
        <div className="min-w-0">
          {eyebrow ? <p className="lens-eyebrow m-0 mb-2">{eyebrow}</p> : null}
          <h2 className="lens-serif m-0 text-2xl text-balance md:text-3xl">{title}</h2>
        </div>
        {aside ? <div className="shrink-0">{aside}</div> : null}
      </div>
      {intro ? <div className="mt-3 max-w-[70ch] text-sm text-muted">{intro}</div> : null}
      <div className="mt-6">{children}</div>
    </section>
  );
}
