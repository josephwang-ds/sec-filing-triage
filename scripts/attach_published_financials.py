#!/usr/bin/env python3
# The published page's attributes are long and use Chinese punctuation.
# ruff: noqa: E501
"""Copy filed-result cards from the published Python pages onto engine snapshots.

The company-page JSON from the read-only parity artifact has prices, filings
and history, but not ``financial_results``: that directory is not in the
Actions cache. The published HTML is the Python renderer's own output, so the
numbers below are read back from the attributes that renderer wrote. Nothing
is recomputed, and a page without a report stays unavailable.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from html import unescape
from pathlib import Path

LABELS = {
    "Revenue": "revenue",
    "Net income": "net_income",
    "Diluted EPS": "eps",
    "Gross profit": "gross_profit",
}
PAIR = re.compile(
    r'data-i18n-en="(?P<en>(?:\\.|[^"\\])*)"\s+data-i18n-zh="(?P<zh>(?:\\.|[^"\\])*)"',
    re.S,
)
CODE = re.compile(r"<code>([^<]+)</code>")
ANCHOR = re.compile(r'<a href="(https://www\.sec\.gov[^"]+)"[^>]*>([^<]*)</a>')


def _attr(value: str) -> str:
    return unescape(value).replace("\\u0026", "&")


def _pairs(fragment: str) -> list[tuple[str, str]]:
    return [(_attr(en), _attr(zh)) for en, zh in PAIR.findall(fragment)]


def _money(english: str, chinese: str, unit: str) -> float | None:
    if unit == "USD/shares":
        match = re.search(r"\$([\d,]+\.\d+)", english)
        return float(match.group(1).replace(",", "")) if match else None
    match = re.search(r"([\d,]+\.\d+)\s*亿美元", chinese)
    if match:
        return float(match.group(1).replace(",", "")) * 1e8
    match = re.search(r"\$([\d,]+\.\d+)B", english)
    return float(match.group(1).replace(",", "")) * 1e9 if match else None


def _percent(text: str) -> float | None:
    match = re.search(r"([+-]\d+\.\d+)%", text)
    return float(match.group(1)) / 100 if match else None


def _reference(english: list[str], as_of: str, sic: str | None) -> dict | None:
    group = sic[:3] if sic and len(sic) == 4 and sic.isdigit() else None
    for line in english:
        available = re.search(
            r"Covered SIC (\d+) sample median YoY: ([+-]\d+\.\d+)% \(n=(\d+), excluding this company\)\. "
            r"Gap: ([+-]\d+\.\d+) percentage points\.",
            line,
        )
        if available:
            return {
                "status": "available",
                "reason": None,
                "sic_group": available.group(1),
                "n": int(available.group(3)),
                "minimum": 5,
                "as_of": as_of,
                "median_yoy": float(available.group(2)) / 100,
                "gap_pp": float(available.group(4)),
                "members": [],
            }
        short = re.search(r"Only (\d+) eligible companies; at least (\d+) required\.", line)
        if short:
            return {
                "status": "unavailable",
                "reason": "insufficient_sample",
                "sic_group": group,
                "n": int(short.group(1)),
                "minimum": int(short.group(2)),
                "as_of": as_of,
                "median_yoy": None,
                "gap_pp": None,
                "members": [],
            }
        if "No comparable company growth rate." in line:
            return {
                "status": "unavailable",
                "reason": "no_company_growth",
                "sic_group": group,
                "n": 0,
                "minimum": 5,
                "as_of": as_of,
                "median_yoy": None,
                "gap_pp": None,
                "members": [],
            }
        if "SEC SIC classification is missing." in line:
            return {
                "status": "unavailable",
                "reason": "missing_classification",
                "sic_group": None,
                "n": 0,
                "minimum": 5,
                "as_of": as_of,
                "median_yoy": None,
                "gap_pp": None,
                "members": [],
            }
    return None


def parse_financial_section(html: str) -> dict | None:
    """Return the engine report dict, or None when this page has no report section."""
    start = html.find('id="earnings"')
    if start < 0:
        return None
    end = html.find("</section>", start)
    section = html[start:end]
    english = [en for en, _zh in _pairs(section)]
    if any(line.startswith("A current financial report is not available") for line in english):
        return {"status": "unavailable", "metrics": [], "reason": "no_report"}
    summary = next(
        (line for line in english if line.startswith(("Quarterly period ended", "Annual period ended"))),
        None,
    )
    if summary is None:
        return None
    match = re.match(
        r"(Quarterly|Annual) period ended (\d{4}-\d{2}-\d{2}) · filed (\d{4}-\d{2}-\d{2}) · (10-[QK]/A|10-[QK])",
        summary,
    )
    if not match:
        return None
    sic_line = next((line for line in english if line.startswith("SEC industry registration:")), "")
    sic_match = re.search(r"\(SIC (\d+)\)", sic_line)
    sic = sic_match.group(1) if sic_match else None
    description = None
    if sic_line:
        named = re.search(r"SEC industry registration: (.+) \(SIC", sic_line)
        description = named.group(1) if named else None
    report_link = re.search(
        r'<a href="(https://www\.sec\.gov[^"]+)"[^>]*>(?:(?!</a>).)*Read the financial report',
        section,
    )
    source = unescape(report_link.group(1)) if report_link else None
    articles = re.findall(r"<article class=\"result-card\">(.*?)</article>", section, re.S)
    metrics = []
    codes = CODE.findall(section)
    code_at = 0
    for article in articles:
        pairs = _pairs(article)
        if not pairs:
            continue
        label = pairs[0][0]
        metric_id = LABELS.get(label)
        if metric_id is None:
            continue
        current = next((pair for pair in pairs if pair[0].startswith("Current:")), None)
        if current is None:
            continue
        period = re.match(r"Current: (\d{4}-\d{2}-\d{2}) — (\d{4}-\d{2}-\d{2}) · (.+)", current[0])
        if period is None:
            continue
        unit = period.group(3)
        value = _money(pairs[1][0], pairs[1][1], unit)
        if value is None:
            continue
        prior_value = None
        prior_end = None
        prior_start = None
        yoy = None
        change = None
        for en, zh in pairs[2:]:
            prior = re.match(r"Prior year \((\d{4}-\d{2}-\d{2})\): (.+)", en)
            if prior:
                prior_end = prior.group(1)
                prior_value = _money(prior.group(2), zh, unit)
            elif en.startswith("Year over year:"):
                yoy = _percent(en)
            elif en.startswith("Change:"):
                change_text = en.split(";", 1)[0].removeprefix("Change:").strip()
                change = _money(change_text, zh, unit)
            elif en.startswith("Prior year:"):
                bounds = re.match(r"Prior year: (\d{4}-\d{2}-\d{2}) — (\d{4}-\d{2}-\d{2})", en)
                if bounds:
                    prior_start, prior_end = bounds.group(1), bounds.group(2)
        if change is None and prior_value is not None:
            change = value - prior_value
        concept = codes[code_at] if code_at < len(codes) else ""
        code_at += 1
        reference = _reference([en for en, _zh in pairs], match.group(3), sic)
        members = []
        for href, text in ANCHOR.findall(article):
            member = re.match(r"([A-Z.]+) · (\d{4}-\d{2}-\d{2}) · ([+-]\d+\.\d+)%", unescape(text).strip())
            if member and reference is not None:
                members.append(
                    {
                        "ticker": member.group(1),
                        "period_end": member.group(2),
                        "yoy": float(member.group(3)) / 100,
                        "source_url": unescape(href),
                    }
                )
        if reference is not None:
            reference["members"] = members
        metrics.append(
            {
                "id": metric_id,
                "concept": concept,
                "unit": unit,
                "value": value,
                "start": period.group(1),
                "end": period.group(2),
                "prior_value": prior_value,
                "prior_start": prior_start,
                "prior_end": prior_end,
                "change": change,
                "yoy": yoy,
                "reference": reference,
            }
        )
    if source is None:
        return None
    if not metrics and not any(
        "comparable numeric facts have not been extracted" in line for line in english
    ):
        return None
    return {
        "status": "available",
        "reason": None,
        "metrics": metrics,
        "form": match.group(4),
        "period_end": match.group(2),
        "filed": match.group(3),
        "period_kind": "annual" if match.group(1) == "Annual" else "quarterly",
        "basis": "as_reported_same_filing",
        "financial_issuer": any("Financial issuers use different revenue" in line for line in english),
        "sic": sic,
        "sic_description": description,
        "source_url": source,
    }


def fetch(origin: str, ticker: str) -> str:
    url = origin.rstrip("/") + "/" + ticker.lower() + ".html"
    request = urllib.request.Request(url, headers={"User-Agent": "CompanyLens financial attach"})
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read().decode("utf-8", "replace")


def attach_tree(source: Path, destination: Path, origin: str, required: list[str]) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    missing = []
    copied = 0
    for path in sorted(source.glob("*.json")):
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        ticker = str(snapshot.get("ticker") or "").upper()
        if ticker.startswith("SYN"):
            raise SystemExit(f"refusing synthetic snapshot {ticker} in {path}")
        try:
            report = parse_financial_section(fetch(origin, ticker))
        except Exception as error:  # noqa: BLE001 - one issuer must not invent a report
            report = None
            print(f"{ticker}: published page not read ({error})", file=sys.stderr)
        if report is None:
            if ticker in required:
                missing.append(ticker)
            report = {"status": "unavailable", "metrics": [], "reason": "published_page_missing"}
        elif report.get("status") != "available" and ticker in required:
            missing.append(ticker)
        snapshot["financial_results"] = report
        (destination / path.name).write_text(json.dumps(snapshot, ensure_ascii=False) + "\n", encoding="utf-8")
        copied += 1
        print(f"{ticker}: {report.get('status')} {report.get('form') or ''}".rstrip())
    if missing:
        raise SystemExit("required issuers have no published financial report: " + ", ".join(missing))
    print(f"attached financial reports onto {copied} snapshot(s) -> {destination}")
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--origin", default="https://company-lens-josephjwang.vercel.app")
    parser.add_argument("--required", nargs="+", default=["AAPL", "JPM", "NVDA"])
    args = parser.parse_args()
    if args.out.resolve() == args.source.resolve():
        raise SystemExit("--out must be a different directory from --source")
    attach_tree(args.source, args.out, args.origin, [ticker.upper() for ticker in args.required])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
