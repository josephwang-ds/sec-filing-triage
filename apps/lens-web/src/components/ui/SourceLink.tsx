interface Props {
  href: string;
  children: string;
  /** Shown to screen readers so a page of "SEC" links is still navigable. */
  describedAs?: string;
}

/** An outbound link to the primary source. Every claim on this site has one. */
export function SourceLink({ href, children, describedAs }: Props) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      aria-label={describedAs}
      className="inline-flex max-w-full items-baseline gap-1 border-b border-accent/40 text-xs break-words text-accent hover:border-accent"
    >
      {children}
      <span aria-hidden="true">↗</span>
    </a>
  );
}
