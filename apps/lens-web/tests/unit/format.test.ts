import { describe, expect, it } from "vitest";
import {
  count,
  filedMoney,
  isoDate,
  isoMinute,
  money,
  multiple,
  percent,
  points,
  signedPercent,
} from "@/lib/format";

/**
 * These assertions are the Python page's output.
 *
 * `company_lens.web.page` formats with `f"{value:+.1%}"` and `f"${value:,.2f}"`,
 * and Python rounds half to even while JavaScript's toFixed does not. The pair
 * of front ends has to print the same literal for the same snapshot, or a
 * parity check between them is comparing rounding modes.
 */
describe("percent formatting", () => {
  it("matches Python's one-decimal percent", () => {
    expect(signedPercent(0.03517043339698933)).toBe("+3.5%");
    expect(signedPercent(-0.24298950901415162)).toBe("-24.3%");
    expect(signedPercent(0)).toBe("0.0%");
    expect(percent(0.25875807288650005)).toBe("25.9%");
    expect(percent(0.8032786885245902, 0)).toBe("80%");
  });

  it("rounds half to even, as Python's format spec does", () => {
    // 0.125 -> 12.5 exactly: Python gives 12.5%, and so must this.
    expect(percent(0.125, 1)).toBe("12.5%");
    // 0.1250 at zero decimals: 12.5 -> 12 (half to even), not 13.
    expect(percent(0.125, 0)).toBe("12%");
    expect(percent(0.135, 0)).toBe("14%");
  });

  it("reports absence rather than zero", () => {
    expect(percent(null)).toBeNull();
    expect(signedPercent(undefined)).toBeNull();
    expect(percent(Number.NaN)).toBeNull();
    expect(percent(Number.POSITIVE_INFINITY)).toBeNull();
  });
});

describe("money formatting", () => {
  it("matches Python's grouped two-decimal dollars", () => {
    expect(money(10351.704333969894)).toBe("$10,351.70");
    expect(money(281.4002473863609)).toBe("$281.40");
    expect(money(1_000_000)).toBe("$1,000,000.00");
  });

  it("writes filed figures the way each language writes them", () => {
    expect(filedMoney(24_318_000_000, "USD", "en")).toBe("$24.32B");
    expect(filedMoney(24_318_000_000, "USD", "zh")).toBe("243.18 亿美元");
    expect(filedMoney(1.42, "USD/shares", "en")).toBe("$1.42 / share");
    expect(filedMoney(1.42, "USD/shares", "zh")).toBe("1.42 美元/股");
  });

  it("keeps the sign on a negative filed figure", () => {
    expect(filedMoney(-2_500_000_000, "USD", "en")).toBe("$-2.50B");
  });
});

describe("other display helpers", () => {
  it("formats multiples, counts and percentage points", () => {
    expect(multiple(0.4618960714913184)).toBe("0.46");
    expect(multiple(0.7637889441294652, 3)).toBe("0.764");
    expect(count(9721)).toBe("9,721");
    expect(points(2.51)).toBe("+2.5");
    expect(points(-2.51)).toBe("-2.5");
  });

  it("slices dates instead of parsing them into a local clock", () => {
    // A filing accepted at 18:33 New York is not the previous day anywhere.
    expect(isoDate("2024-09-23T18:33:00-04:00")).toBe("2024-09-23");
    expect(isoMinute("2024-12-31T10:05:00-05:00")).toBe("2024-12-31 10:05");
    expect(isoDate(null)).toBeNull();
  });
});
