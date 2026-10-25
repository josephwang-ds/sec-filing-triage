import type { ReactNode } from "react";

interface Props {
  caption: string;
  headers: string[];
  rows: (ReactNode | string | null)[][];
  /** Column index that holds the row's label; it stays readable when scrolled. */
  labelColumn?: number;
}

/**
 * A long evidence table that survives a phone.
 *
 * Tables of eight numeric columns cannot reflow into 375px without becoming
 * unreadable, so the table scrolls inside its own container rather than
 * widening the page, and the caption says what it is before the reader gets
 * there. `min-width: 0` on the wrapper is what keeps the scroll inside the
 * grid cell instead of pushing the layout sideways.
 */
export function EvidenceTable({ caption, headers, rows, labelColumn = 0 }: Props) {
  return (
    <figure className="m-0 min-w-0">
      <figcaption className="mb-2 text-xs text-muted">{caption}</figcaption>
      <div className="min-w-0 overflow-x-auto rounded-card border border-line">
        <table className="w-full min-w-[640px] border-collapse text-sm">
          <thead>
            <tr className="bg-panel-muted text-left">
              {headers.map((header) => (
                <th
                  key={header}
                  scope="col"
                  className="border-b border-line px-3 py-2 text-[11px] font-bold tracking-wide text-muted uppercase"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex} className="odd:bg-panel even:bg-panel-muted/60">
                {row.map((cell, cellIndex) =>
                  cellIndex === labelColumn ? (
                    <th
                      key={cellIndex}
                      scope="row"
                      className="border-b border-line px-3 py-2 text-left align-top text-sm font-bold"
                    >
                      {cell}
                    </th>
                  ) : (
                    <td
                      key={cellIndex}
                      className="lens-figure border-b border-line px-3 py-2 align-top text-sm"
                    >
                      {cell ?? "—"}
                    </td>
                  ),
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}
