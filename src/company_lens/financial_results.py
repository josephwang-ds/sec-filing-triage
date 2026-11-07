"""Actual filed financial results; no estimated dates or investment signals."""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

CONCEPTS = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "Revenues",
    ),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "eps": ("EarningsPerShareDiluted",),
    "gross_profit": ("GrossProfit",),
}


def report_path(root: str | Path, ticker: str) -> Path:
    return Path(root) / "financial_results" / f"{ticker.lower()}.json"


def latest_report(submissions: dict, cik: int) -> dict | None:
    recent = submissions.get("filings", {}).get("recent", {})
    records = []
    for index, form in enumerate(recent.get("form", [])):
        if form not in {"10-Q", "10-K", "10-Q/A", "10-K/A"}:
            continue

        def value(key: str, row: int = index) -> str:
            values = recent.get(key, [])
            return str(values[row]) if row < len(values) else ""

        end, filed = value("reportDate"), value("filingDate")
        accession, document = value("accessionNumber"), value("primaryDocument")
        try:
            date.fromisoformat(end)
            date.fromisoformat(filed)
        except ValueError:
            continue
        if not accession or not document:
            continue
        records.append(
            {
                "form": form,
                "period_end": end,
                "filed": filed,
                "accession": accession,
                "source_url": f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                f"{accession.replace('-', '')}/{document}",
            }
        )
    # An amendment to an older period must not displace a newer quarter.
    return max(records, key=lambda row: (row["period_end"], row["filed"])) if records else None


def build_financial_results(facts: dict, submissions: dict, cik: int) -> dict:
    report = latest_report(submissions, cik)
    if not report:
        return {"status": "unavailable", "metrics": [], "reason": "no_report"}
    annual = report["form"].startswith("10-K")
    metrics = []
    financial_issuer = str(submissions.get("sic", "")).startswith("6")
    for metric, concepts in CONCEPTS.items():
        if financial_issuer and metric in {"revenue", "gross_profit"}:
            continue
        unit = "USD/shares" if metric == "eps" else "USD"
        for concept in concepts:
            rows = (
                facts.get("facts", {})
                .get("us-gaap", {})
                .get(concept, {})
                .get("units", {})
                .get(unit, [])
            )
            candidates = [row for row in rows if _usable(row, report, annual)]
            current = [row for row in candidates if row["end"] == report["period_end"]]
            if not current:
                continue
            # Prefer the duration nearest a normal fiscal quarter/year.
            now = min(current, key=lambda row: abs(_duration(row) - (365 if annual else 91)))
            prior = [
                row
                for row in candidates
                if 330
                <= (date.fromisoformat(now["end"]) - date.fromisoformat(row["end"])).days
                <= 400
                and abs(_duration(row) - _duration(now)) <= 10
            ]
            before = (
                min(
                    prior,
                    key=lambda row: abs(
                        (date.fromisoformat(now["end"]) - date.fromisoformat(row["end"])).days - 365
                    ),
                )
                if prior
                else None
            )
            old = float(before["val"]) if before else None
            current_value = float(now["val"])
            metrics.append(
                {
                    "id": metric,
                    "concept": concept,
                    "unit": unit,
                    "value": current_value,
                    "start": now["start"],
                    "end": now["end"],
                    "prior_value": old,
                    "prior_start": before["start"] if before else None,
                    "prior_end": before["end"] if before else None,
                    "change": None if old is None else current_value - old,
                    # A loss/zero base does not produce a meaningful growth percentage.
                    "yoy": (current_value / old - 1)
                    if old is not None and old > 0 and current_value >= 0
                    else None,
                }
            )
            break
    return {
        **report,
        "status": "available" if metrics else "metadata_only",
        "period_kind": "annual" if annual else "quarterly",
        "metrics": metrics,
        "basis": "as_reported_same_filing",
        "reason": None,
        "financial_issuer": financial_issuer,
        "sic": str(submissions.get("sic", "")),
        "cik": str(cik),
        "sic_description": str(submissions.get("sicDescription", "")),
    }


def _duration(row: dict) -> int:
    return (date.fromisoformat(row["end"]) - date.fromisoformat(row["start"])).days


def _usable(row: dict, report: dict, annual: bool) -> bool:
    if row.get("accn") != report["accession"] or row.get("filed", "") > report["filed"]:
        return False
    try:
        duration = _duration(row)
        value = float(row["val"])
    except (ValueError, TypeError, KeyError):
        return False
    # Never mix a 6/9-month cumulative fact into a standalone quarter.
    return math.isfinite(value) and (
        (330 <= duration <= 400) if annual else (70 <= duration <= 110)
    )


def save_financial_results(payload: dict, root: str | Path, ticker: str) -> None:
    target = report_path(root, ticker)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.part")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temporary.replace(target)


def filed_figures_status(report: dict | None) -> str:
    """Separate a filing, displayable figures, and an absence.

    ``numbers`` is a structured available report with at least one metric.
    ``filing_only`` is a filing whose figures were not extracted.
    ``display_fallback`` is rounded text read back from a published page.
    ``unavailable`` means no current report.
    """
    if not report or report.get("status") in {None, "unavailable"}:
        return "unavailable"
    if report.get("extraction") == "published_html_fallback":
        return "display_fallback"
    metrics = report.get("metrics") or []
    if report.get("status") == "available" and metrics:
        return "numbers"
    return "filing_only"


def load_financial_results(root: str | Path, ticker: str) -> dict | None:
    path = report_path(root, ticker)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
