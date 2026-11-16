interface Props {
  label: string;
  sections: { id: string; label: string }[];
}

/** Anchor navigation for a long page. Scrolls on a phone, sticks on a desktop. */
export function PageNav({ label, sections }: Props) {
  return (
    <nav
      aria-label={label}
      className="mb-8 flex gap-1 overflow-x-auto border-y border-line py-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {sections.map((section) => (
        <a
          key={section.id}
          href={`#${section.id}`}
          className="shrink-0 rounded-md px-2.5 py-1 text-xs font-bold whitespace-nowrap text-muted hover:bg-panel hover:text-ink"
        >
          {section.label}
        </a>
      ))}
    </nav>
  );
}
