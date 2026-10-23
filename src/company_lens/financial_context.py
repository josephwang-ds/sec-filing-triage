"""Inspectable comparisons within the site's covered SEC SIC groups."""

from __future__ import annotations

import copy
import math
from datetime import date
from pathlib import Path
from statistics import median

from company_lens.financial_results import load_financial_results
from company_lens.universe import supported_companies

MIN_PEERS = 5


def with_financial_context(root: str | Path, ticker: str) -> dict | None:
    report = load_financial_results(root, ticker)
    if not report or report.get("status") != "available":
        return report
    report = copy.deepcopy(report)
    sic = str(report.get("sic", ""))
    group = sic[:3] if len(sic) == 4 and sic.isdigit() else None
    universe = Path(root) / "universe.csv"
    covered = {c.ticker for c in supported_companies(universe)} if universe.exists() else None
    candidates = []
    seen = {str(report.get("cik") or ticker.upper())}
    if group:
        for path in sorted((Path(root) / "financial_results").glob("*.json")):
            if covered is not None and path.stem.upper() not in covered:
                continue
            if path.stem.upper() == ticker.upper():
                continue
            peer = load_financial_results(root, path.stem)
            if not peer or peer.get("status") != "available":
                continue
            issuer = str(peer.get("cik") or path.stem.upper())
            if issuer in seen:
                continue
            if str(peer.get("sic", ""))[:3] != group:
                continue
            if peer.get("period_kind") != report["period_kind"]:
                continue
            # A later filing must not appear as if it was known on the issuer's filing date.
            if peer["filed"] > report["filed"]:
                continue
            if abs((_day(peer["period_end"]) - _day(report["period_end"])).days) > 45:
                continue
            seen.add(issuer)
            candidates.append((path.stem.upper(), peer))
    for metric in report["metrics"]:
        if metric["id"] not in {"revenue", "net_income"}:
            continue
        members = []
        for symbol, peer in candidates:
            for item in peer["metrics"]:
                if (
                    item["id"] == metric["id"]
                    and item["concept"] == metric["concept"]
                    and item["unit"] == metric["unit"]
                    and _valid_growth(item)
                    and abs(_duration(item) - _duration(metric)) <= 15
                    and abs(
                        (_day(item["prior_end"])
                         - _day(metric["prior_end"] or metric["end"])).days
                    ) <= 45
                ):
                    members.append({"ticker": symbol, "yoy": item["yoy"],
                                    "period_end": item["end"], "filed": peer["filed"],
                                    "source_url": peer["source_url"]})
                    break
        available = _valid_growth(metric) and len(members) >= MIN_PEERS
        center = median(member["yoy"] for member in members) if available else None
        metric["reference"] = {
            "status": "available" if available else "unavailable",
            "reason": None if available else (
                "no_company_growth" if not _valid_growth(metric) else
                "missing_classification" if not group else "insufficient_sample"
            ),
            "sic_group": group, "n": len(members), "minimum": MIN_PEERS,
            "as_of": report["filed"], "median_yoy": center,
            "gap_pp": (metric["yoy"] - center) * 100 if available else None,
            "members": members,
        }
    return report


def _day(value: str) -> date:
    return date.fromisoformat(value)


def _duration(metric: dict) -> int:
    return (_day(metric["end"]) - _day(metric["start"])).days


def _valid_growth(metric: dict) -> bool:
    value = metric.get("yoy")
    return isinstance(value, (int, float)) and math.isfinite(value)
