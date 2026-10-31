"""Prepare an old-page/new-page comparison: render the Python page, list what must match.

Both front ends read one snapshot, so a number that differs between them is a
migration defect rather than a difference of opinion. This half renders the
Python page for each snapshot and writes the display literals the engine
produces from it. `apps/lens-web/scripts/parity.mjs` then opens both pages in a
browser and compares what each actually shows.

Two pages, one browser, because neither side can be compared as static text:
the Python page fills its history section in from an inline JSON block after
load, and the Next.js page carries its own values in a serialised payload.
Comparing the rendered DOM is the only comparison that answers the question.

    python scripts/compare_lens_pages.py
    node apps/lens-web/scripts/parity.mjs --base-url http://127.0.0.1:4320
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from company_lens.contracts import CompanySnapshot
from company_lens.web.page import _default_period, _money, render_company_page

TAGS = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Check:
    name: str
    literal: str


def text_of(html: str) -> str:
    body = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    body = re.sub(r"<style.*?</style>", " ", body, flags=re.S)
    return SPACE.sub(" ", TAGS.sub(" ", body))


def percent(value: float | None) -> str | None:
    """`Intl.NumberFormat` percent, signDisplay exceptZero, at most one decimal.

    The history section is rendered in the browser on the Python page, so this
    is what a reader sees there: `+49%`, not `+49.0%`. Both front ends have to
    print it the same way or a parity run reports a difference of convention as
    a difference of number.
    """
    if value is None:
        return None
    body = f"{float(value) * 100:.1f}".rstrip("0").rstrip(".")
    sign = "+" if float(value) > 0 else ""
    return f"{sign}{body}%"


def plain_percent(value: float | None, digits: int = 1) -> str | None:
    if value is None:
        return None
    return f"{float(value) * 100:.{digits}f}".rstrip("0").rstrip(".") + "%"


def whole_money(value: float | None) -> str | None:
    return None if value is None else f"${round(float(value)):,}"


def points(value: float | None) -> str | None:
    """The return gap, in percentage points: `(gap * 100).toFixed(1)`."""
    return None if value is None else f"{float(value) * 100:.1f}"


def checks_for(snapshot: dict) -> list[Check]:
    """The values a reader would notice changing."""
    period_label = _default_period(_as_contract(snapshot))
    option = snapshot["period_options"][period_label]
    performance = option["performance"]
    asset = performance["asset"]
    market = performance["benchmark"]

    found = [
        Check("latest close", _money(float(snapshot["market"]["latest_adjusted_close"]))),
        Check("ending value", whole_money(performance["ending_value"])),
        Check("total return", percent(asset["total_return"])),
        Check("benchmark return", percent(market["total_return"])),
        Check("return gap (percentage points)", points(performance["relative_total_return"])),
        Check("annualised volatility", plain_percent(asset["annualized_volatility"])),
        Check("max drawdown", percent(asset["max_drawdown"])),
        Check("period start", option["period"]["start"]),
        Check("period end", option["period"]["end"]),
        Check("as of", snapshot["as_of"]),
    ]
    for filing in snapshot.get("latest_filings", [])[:3]:
        # The accession is text on both pages; the source URL is an href, and
        # is compared as a link rather than as a string in the prose.
        found.append(Check(f"filing {filing['accession']}", filing["accession"]))
    report = snapshot.get("financial_results") or {}
    if report.get("status") == "available":
        for metric in report["metrics"]:
            # Both pages write billions in English; the figure must match.
            found.append(
                Check(
                    f"filed {metric['id']}",
                    f"${metric['value'] / 1e9:,.2f}B"
                    if metric["unit"] != "USD/shares"
                    else f"${metric['value']:,.2f}",
                )
            )
            found.append(Check(f"filed {metric['id']} period", metric["end"]))
    return [check for check in found if check.literal]


def _as_contract(snapshot: dict) -> CompanySnapshot:
    """Enough of a snapshot for `_default_period`, without rebuilding the whole model."""

    class View:
        period = snapshot["period"]
        period_options = snapshot["period_options"]

    return View()  # type: ignore[return-value]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", type=Path, default=Path("apps/lens-web/fixtures/snapshots"))
    parser.add_argument("--out", type=Path, default=Path("data/build/parity"))
    args = parser.parse_args()

    files = sorted(args.snapshots.glob("*.json"))
    if not files:
        print(f"no snapshots in {args.snapshots}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    cases = []
    for file in files:
        snapshot = json.loads(file.read_text(encoding="utf-8"))
        ticker = str(snapshot["ticker"])
        old_page = render_company_page(_rebuild(snapshot), args.out / f"{ticker.lower()}-old.html")
        urls = [filing["source_url"] for filing in snapshot.get("latest_filings", [])[:3]]
        cases.append(
            {
                "ticker": ticker,
                "old_page": str(Path(old_page).resolve()),
                "period": _default_period(_as_contract(snapshot)),
                "literals": [
                    {"name": check.name, "literal": check.literal} for check in checks_for(snapshot)
                ],
                "links": urls,
            }
        )
        print(f"{ticker}: rendered {old_page}, {len(cases[-1]['literals'])} literals to match")

    manifest = args.out / "expected.json"
    manifest.write_text(json.dumps(cases, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nexpectations -> {manifest}")
    print("now run: node apps/lens-web/scripts/parity.mjs")
    return 0


def _rebuild(payload: dict) -> CompanySnapshot:
    """Rebuild the dataclass the Python renderer expects from a snapshot document."""
    from company_lens.contracts import (
        Citation,
        EvidenceScopeSummary,
        FilingBrief,
        FilingChange,
        FilingComparison,
        FilingEntity,
        FilingReaction,
        FilingTimelinePoint,
        HeadlineBrief,
    )

    def citation(value):
        return None if value is None else Citation(**value)

    def reaction(value):
        return None if value is None else FilingReaction(**value)

    def brief(value):
        comparison = value.get("comparison")
        return FilingBrief(
            accession=value["accession"],
            form=value["form"],
            accepted_at=value["accepted_at"],
            items=value["items"],
            source_url=value["source_url"],
            novelty=value.get("novelty"),
            key_numbers=value.get("key_numbers", []),
            entities=[FilingEntity(**entity) for entity in value.get("entities", [])],
            passages=[Citation(**passage) for passage in value.get("passages", [])],
            comparison=None
            if comparison is None
            else FilingComparison(
                comparable_key=comparison["comparable_key"],
                prior_accession=comparison["prior_accession"],
                prior_accepted_at=comparison["prior_accepted_at"],
                prior_source_url=comparison["prior_source_url"],
                changes=[
                    FilingChange(
                        kind=change["kind"],
                        current=citation(change.get("current")),
                        prior=citation(change.get("prior")),
                        similarity=change.get("similarity"),
                    )
                    for change in comparison.get("changes", [])
                ],
                counts=comparison.get("counts", {}),
            ),
            reaction=reaction(value.get("reaction")),
        )

    scope = payload.get("evidence_scope")
    return CompanySnapshot(
        schema_version=payload["schema_version"],
        ticker=payload["ticker"],
        company_name=payload["company_name"],
        as_of=payload["as_of"],
        benchmark=payload["benchmark"],
        period=payload["period"],
        profile=payload["profile"],
        market=payload["market"],
        performance=payload["performance"],
        growth=payload["growth"],
        period_options=payload["period_options"],
        latest_filings=[brief(filing) for filing in payload.get("latest_filings", [])],
        explanation=payload.get("explanation", {}),
        provenance=payload.get("provenance", {}),
        warnings=payload.get("warnings", []),
        filing_timeline=[
            FilingTimelinePoint(
                accession=point["accession"],
                accepted_at=point["accepted_at"],
                item_code=point["item_code"],
                item_label=point["item_label"],
                source_url=point["source_url"],
                reaction=reaction(point.get("reaction")),
                item_label_zh=point.get("item_label_zh"),
            )
            for point in payload.get("filing_timeline", [])
        ],
        evidence_scope=None if scope is None else EvidenceScopeSummary(**scope),
        headlines=[HeadlineBrief(**row) for row in payload.get("headlines", [])],
        market_headlines=[HeadlineBrief(**row) for row in payload.get("market_headlines", [])],
        fundamentals=None,
        disclosure_signal=payload.get("disclosure_signal"),
        volatility_forecast=payload.get("volatility_forecast"),
        benchmark_comparisons=payload.get("benchmark_comparisons", {}),
        financial_results=payload.get("financial_results"),
    )


if __name__ == "__main__":
    raise SystemExit(main())
