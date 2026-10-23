"""The filed financial cards and their sample references as citable AI evidence."""

from __future__ import annotations

from typing import Any

from company_lens.web.financials import DEFINITIONS, LABELS, _money

FINANCIAL_RESULTS_LIMIT = (
    "Financial results are as reported in the identified 10-Q/10-K, including its own "
    "prior-year comparatives; keep these separate from latest-restated annual fundamentals "
    "and earnings announcements in 8-K. State the actual period, currency and YoY basis. "
    "Covered SIC sample medians are equal-weight company growth rates, not aggregate "
    "industry growth or curated business peers. State the sample size and reference as-of "
    "date. Reference gaps use percentage points, not percent; financial growth is not a "
    "stock return. An unavailable reference supplies no median or gap: explain the reason, "
    "never compute or invent a replacement. The data establishes changes, not their "
    "causes, consensus beats, guidance, valuation or investment conclusions."
)


def financial_results_packet(
    report: dict | None, ticker: str, citations: dict[str, dict[str, str]]
) -> dict[str, Any]:
    page = f"/{ticker.lower()}.html#earnings"
    coverage = "metric:financial_results.coverage"
    citations[coverage] = {
        "label": "Financial report coverage", "label_zh": "财报数据覆盖情况",
        "url": page, "section": "financial_results",
    }
    if not report or report.get("status") == "unavailable":
        return {"status": "unavailable", "citation": coverage,
                "reason": "No current filed financial results are available in this snapshot."}
    source = "source:financial_report"
    citations[source] = {
        "label": "Latest quarterly/annual report", "label_zh": "最新季报/年报原文",
        "url": report["source_url"], "section": "financial_results",
    }
    packet: dict[str, Any] = {
        "status": report["status"], "citation": source,
        "form": report["form"], "period_kind": report["period_kind"],
        "period_end": report["period_end"], "filed": report["filed"],
        "basis": "as_reported_same_filing",
        "financial_issuer": bool(report.get("financial_issuer")),
        "dates_zh": {"period_end": _date_zh(report["period_end"]),
                     "filed": _date_zh(report["filed"])},
        "metrics": [],
    }
    if report.get("financial_issuer"):
        packet["coverage_note"] = (
            "Generic revenue and gross-profit comparisons are omitted for financial issuers "
            "because their revenue definitions differ."
        )
    for metric in report.get("metrics", []):
        key, unit = metric["id"], metric["unit"]
        citation = f"metric:financial_results.{key}"
        en, zh = LABELS[key]
        citations[citation] = {
            "label": f"Filed {en.lower()} and YoY", "label_zh": f"财报{zh}与同比",
            "url": report["source_url"], "section": "financial_results",
        }
        item: dict[str, Any] = {
            "metric": key, "label": en, "label_zh": zh,
            "definition": DEFINITIONS[key][0], "concept": metric["concept"],
            "unit": unit, "citation": citation, "source_citation": source,
            "current_period": {"start": metric["start"], "end": metric["end"]},
            "current": _value(metric["value"], unit),
            "yoy_definition": "Current / same period a year earlier - 1; not quarter on quarter.",
        }
        if metric["prior_value"] is not None:
            item["prior_period"] = {"start": metric["prior_start"], "end": metric["prior_end"]}
            item["prior"] = _value(metric["prior_value"], unit)
            item["absolute_change"] = _value(metric["change"], unit)
        if metric["yoy"] is not None:
            item["yoy"] = f"{metric['yoy']:+.1%}"
        else:
            item["yoy_unavailable_reason"] = (
                "No same-filing prior-year comparison, a zero base, or a loss; "
                "do not calculate a growth percentage."
            )
        reference = metric.get("reference")
        if reference:
            item["category_reference"] = _reference(reference, key, en, zh, page, citations)
        else:
            item["category_reference"] = {"status": "unavailable", "reason": "not_provided"}
        packet["metrics"].append(item)
    return packet


def _value(value: float, unit: str) -> dict[str, str]:
    return {"display_value": _money(value, unit), "display_value_zh": _money(value, unit, True)}


def _reference(reference, key, en, zh, page, citations) -> dict:
    citation = f"metric:financial_reference.{key}"
    citations[citation] = {
        "label": f"Covered sample: {en.lower()}", "label_zh": f"本站类别样本: {zh}",
        "url": page, "section": "financial_results",
    }
    packet = {
        "status": reference["status"], "reason": reference.get("reason"),
        "citation": citation, "sic_group": reference.get("sic_group"),
        "sample_size": reference["n"], "minimum_sample_size": reference["minimum"],
        "as_of": reference["as_of"],
        "method": (
            "Latest cached reports of other covered issuers; same first three SEC SIC digits, "
            "exact accounting concept, currency and annual/quarterly grain. Current and prior "
            "period ends within 45 days; current durations within 15 days. No filings after "
            "the reference as-of date. CIK deduplicates share classes. Missing comparisons "
            "and zero/loss-base growth excluded. Equal-weight median, not aggregate industry "
            "growth or a whole-industry census. Historical peer filings are not reconstructed."
        ),
    }
    if reference["status"] != "available":
        return packet
    packet.update({
        "median_yoy": f"{reference['median_yoy']:+.1%}",
        "gap": f"{reference['gap_pp']:+.1f} percentage points",
        "gap_zh": f"{reference['gap_pp']:+.1f} 个百分点",
        "gap_definition": "Company YoY minus sample median YoY, in percentage points.",
        "members": [],
    })
    for member in reference["members"]:
        source = f"source:financial_peer.{member['ticker']}.{key}"
        citations[source] = {
            "label": f"{member['ticker']} {en.lower()} source",
            "label_zh": f"{member['ticker']} {zh}来源",
            "url": member["source_url"], "section": "financial_results",
        }
        packet["members"].append({
            "ticker": member["ticker"], "period_end": member["period_end"],
            "filed": member["filed"], "yoy": f"{member['yoy']:+.1%}", "citation": source,
        })
    return packet


def _date_zh(value: str) -> str:
    year, month, day = value.split("-")
    return f"{year}年{int(month)}月{int(day)}日"
