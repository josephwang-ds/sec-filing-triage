/**
 * Display formatting, and nothing else.
 *
 * Every value that reaches these helpers was already computed by the Python
 * engine. They choose how many digits to show; they never change a number,
 * derive one, or fill a missing one in. `null` in, absence out.
 *
 * The digit counts and the rounding match `src/company_lens/web/page.py` so the
 * two front ends print the same literals: Python's format spec rounds half to
 * even, JavaScript's `toFixed` does not, and a reader comparing the old page
 * with the new one over the same snapshot should not find 12.5% on one and
 * 12.6% on the other.
 */

/** Python's `format(value, f".{digits}f")`: round half to even. */
function fixedHalfEven(value: number, digits: number): string {
  if (!Number.isFinite(value)) return "";
  const factor = 10 ** digits;
  const scaled = value * factor;
  const floor = Math.floor(scaled);
  const diff = scaled - floor;
  let rounded: number;
  const epsilon = 1e-9;
  if (Math.abs(diff - 0.5) < epsilon) {
    rounded = floor % 2 === 0 ? floor : floor + 1;
  } else {
    rounded = Math.round(scaled);
  }
  const result = rounded / factor;
  return result.toFixed(digits);
}

export function percent(value: number | null | undefined, digits = 1): string | null {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  return `${fixedHalfEven(value * 100, digits)}%`;
}

/**
 * `+3.5%` / `-24.3%`, and a bare `0.0%` for an exact zero.
 *
 * The sign is the point: a relative return without one reads as a gain.
 */
export function signedPercent(value: number | null | undefined, digits = 1): string | null {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  if (value === 0) return `${(0).toFixed(digits)}%`;
  const body = fixedHalfEven(Math.abs(value) * 100, digits);
  return `${value > 0 ? "+" : "-"}${body}%`;
}

export function money(value: number | null | undefined): string | null {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  const [whole, fraction] = fixedHalfEven(value, 2).split(".");
  const grouped = (whole ?? "0").replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `$${grouped}.${fraction ?? "00"}`;
}

export function multiple(value: number | null | undefined, digits = 2): string | null {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  return fixedHalfEven(value, digits);
}

export function count(value: number | null | undefined): string | null {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  return Math.round(value).toLocaleString("en-US");
}

/**
 * The calendar day, as the snapshot states it.
 *
 * ISO, in both languages, and never re-parsed into a local clock: these are US
 * market dates and SEC acceptance timestamps, and turning `2024-12-31` into a
 * Date in a browser two time zones away is how a filing moves to the day
 * before. The string is sliced, not converted.
 */
export function isoDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const match = /^(\d{4}-\d{2}-\d{2})/.exec(value);
  return match ? (match[1] ?? null) : null;
}

/** `2024-12-31 10:05` in the filing's own stated offset, with the offset kept. */
export function isoMinute(value: string | null | undefined): string | null {
  if (!value) return null;
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(value);
  if (!match) return isoDate(value);
  return `${match[1]} ${match[2]}`;
}
