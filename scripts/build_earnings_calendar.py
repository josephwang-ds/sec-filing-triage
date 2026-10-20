"""A page for when each issuer is next expected to report.

Estimates, not announced dates, and the page says so at the top rather than in a
footnote. Nothing here queries a vendor calendar: the estimate comes from each
issuer's own filing history, which is the same source the model's features use,
so the page and the pipeline cannot drift apart.

Measured on 3,257 out-of-sample predictions from this universe, the annual anchor
misses by a median of one day, lands within three days 60% of the time, and
within a week 77%. The remaining quarter miss by more, which is why the page
shows a week rather than a date and prints the confidence beside every row.
"""

from __future__ import annotations

import argparse
import html
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from filing_triage.earnings import expected_next_report

ACCURACY = {"within_3_days": 0.60, "within_7_days": 0.77, "median_error_days": 1}


def _confidence(row) -> tuple[str, str]:
    """A label and a class, from how much history stands behind the estimate."""
    if row["method"] != "annual anchor":
        return "cadence only", "low"
    if row["prior_reports"] >= 8:
        return "annual anchor", "high"
    return "annual anchor", "medium"


def render(table: pd.DataFrame, as_of: pd.Timestamp, horizon: int) -> str:
    upcoming = table[table["days_until"] <= horizon]
    rows = []
    for _, row in upcoming.iterrows():
        label, level = _confidence(row)
        when = row["expected"]
        window = (f"{(when - pd.Timedelta(days=3)):%b %-d}"
                  f" &ndash; {(when + pd.Timedelta(days=3)):%b %-d}")
        rows.append(
            f"<tr class='{level}'>"
            f"<td class='ticker'>{html.escape(row['ticker'])}</td>"
            f"<td class='window'>{window}</td>"
            f"<td class='num'>{int(row['days_until'])}</td>"
            f"<td class='date'>{row['last_report']:%Y-%m-%d}</td>"
            f"<td class='conf'><span class='dot'></span>{label}"
            f" · {int(row['prior_reports'])} prior</td></tr>"
        )
    body = "".join(rows) or (
        "<tr><td colspan='5' class='empty'>No issuer is expected to report "
        "within this horizon.</td></tr>")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Expected earnings</title>
<style>
:root{{--paper:#f5f4ec;--panel:#fff;--ink:#183c35;--ink2:#526558;--muted:#657567;
--rule:#d8ddd3;--accent:#426b50;--warn:#c8392f;--ok:#2f7a55;--amber:#a8781f}}
@media(prefers-color-scheme:dark){{:root{{--paper:#101e19;--panel:#172c23;--ink:#f7f7f4;
--ink2:#c3c2b7;--rule:#33322f;--accent:#b4cd8c;--warn:#e88079;--ok:#6bbd92;--amber:#d6a94a}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);
font:400 15px/1.6 -apple-system,"Segoe UI",sans-serif}}
.wrap{{max-width:760px;margin:0 auto;padding:48px 20px 80px}}
h1{{font-size:28px;margin:0 0 6px;letter-spacing:-.01em}}
.sub{{color:var(--muted);font-size:13px;margin:0 0 28px}}
.banner{{padding:16px 18px;border:1px solid var(--rule);background:var(--panel);
margin-bottom:28px;font-size:14px;line-height:1.65}}
.banner b{{color:var(--warn)}}
.banner .acc{{display:block;margin-top:8px;color:var(--muted);font-size:13px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
th{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--ink);
font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:600}}
td{{padding:11px 10px;border-bottom:1px solid var(--rule)}}
td.ticker{{font-weight:700}}
td.window{{font-variant-numeric:tabular-nums}}
td.num,td.date{{font-variant-numeric:tabular-nums;color:var(--ink2)}}
td.conf{{color:var(--muted);font-size:12px;white-space:nowrap}}
.dot{{display:inline-block;width:7px;height:7px;border-radius:50%;
margin-right:6px;vertical-align:middle}}
tr.high .dot{{background:var(--ok)}}
tr.medium .dot{{background:var(--amber)}}
tr.low .dot{{background:var(--warn)}}
td.empty{{color:var(--muted);text-align:center;padding:32px}}
footer{{margin-top:32px;padding-top:16px;border-top:1px solid var(--rule);
color:var(--muted);font-size:12px}}
@media(max-width:560px){{td.date,th.date{{display:none}}}}
</style></head><body><div class="wrap">
<h1>Expected earnings</h1>
<p class="sub">{len(upcoming)} of {len(table)} issuers · next {horizon} days ·
as of {as_of:%Y-%m-%d}</p>

<div class="banner">
<b>These are estimates, not announced dates.</b> Each one is this issuer's
corresponding quarter a year ago, rolled forward — inferred from its own filing
history, never from a vendor calendar. An issuer that moves its reporting date
will not be caught here until it has filed.
<span class="acc">Measured on {3257:,} out-of-sample predictions from this
universe: median miss {ACCURACY['median_error_days']} day,
{ACCURACY['within_3_days']:.0%} within three days,
{ACCURACY['within_7_days']:.0%} within a week. The window shown is ±3 days.</span>
</div>

<table><thead><tr>
<th>Issuer</th><th>Expected window</th><th>Days</th>
<th class="date">Last report</th><th>Confidence</th>
</tr></thead><tbody>{body}</tbody></table>

<footer>Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC from Item 2.02 filings in
the local EDGAR build. Green: annual anchor with eight or more prior reports.
Amber: annual anchor, less history. Red: too little history for the annual
anchor, quarterly cadence used instead.</footer>
</div></body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path,
                        default=Path("data/build/events.parquet"))
    parser.add_argument("--out", type=Path,
                        default=Path("data/build/company_pages/earnings.html"))
    parser.add_argument("--horizon", type=int, default=90,
                        help="how many days ahead to list")
    parser.add_argument("--as-of", default=None,
                        help="pretend today is this date (YYYY-MM-DD)")
    args = parser.parse_args()

    events = pd.read_parquet(args.events)
    as_of = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp.today()
    table = expected_next_report(events, as_of=as_of)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(table, as_of.normalize(), args.horizon),
                        encoding="utf-8")
    shown = int((table["days_until"] <= args.horizon).sum())
    print(f"expected-earnings page: {shown} of {len(table)} issuers "
          f"within {args.horizon} days -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
