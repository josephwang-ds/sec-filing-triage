"""Build the compact, immutable evidence maps used by the public Q&A function.

One map per **evidence scope**. A visitor chooses how wide the model is allowed
to look -- filings and fundamentals only, plus company news, plus market context,
or everything -- and the server sends exactly that subset.

The scopes are not a display filter. Each one carries its own
`allowed_citations` and `allowed_number_literals`, computed from the sections it
actually contains, because those two lists are what the response validator
enforces. Sending the narrow evidence while validating against the wide lists
would let a model cite a headline it was never shown and have the citation pass
-- which is the one failure this whole mechanism exists to prevent.

Each scope is therefore materialised in full rather than assembled from shared
parts at request time. It costs about four megabytes across the whole universe
and one JSON parse per cold start, and it buys the guarantee that the evidence
the model reads and the lists it is judged against were built together, in one
language, from one function.
"""

from __future__ import annotations

import json
from typing import Any

from company_lens.llm.grounded import NUMBER_LITERAL, localized_month_number_literals
from company_lens.web.financial_evidence import FINANCIAL_RESULTS_LIMIT, financial_results_packet

ASK_EVIDENCE_VERSION = "company-lens.ask-evidence.v4"

DEFAULT_SCOPE = "core"

# Which optional news sections each scope adds to the always-present core of
# profile, performance, fundamentals and latest filing.
#
# "market" deliberately does not include company news. Read cumulatively the
# four scopes would collapse to three -- the widest would be identical to the
# one below it -- so each is a distinct question a visitor might actually have:
# the company's own numbers, what is being written about the company, what is
# happening around it, or all of that at once.
SCOPE_SECTIONS: dict[str, tuple[str, ...]] = {
    "core": (),
    "company": ("company_headlines",),
    "market": ("market_headlines",),
    "all": ("company_headlines", "market_headlines"),
}

SCOPE_LABELS: dict[str, dict[str, str]] = {
    "core": {"en": "Core financials", "zh": "核心财务"},
    "company": {"en": "Company news", "zh": "公司动态"},
    "market": {"en": "Market context", "zh": "市场背景"},
    "all": {"en": "All evidence", "zh": "全部证据"},
}

SCOPE_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "core": {
        "en": ("SEC filings, filed financial results, covered-sample comparisons "
               "and long-term fundamentals."),
        "zh": "SEC 披露、财报数据、本站类别样本比较与长期基本面。",
    },
    "company": {
        "en": "Core financials plus recent headlines about this company.",
        "zh": "核心财务,加上该公司的近期新闻。",
    },
    "market": {
        "en": "Core financials plus broad market and sector headlines.",
        "zh": "核心财务,加上行业与宏观新闻。",
    },
    "all": {
        "en": "Core financials, company news and market context together.",
        "zh": "核心财务、公司动态与市场背景的组合。",
    },
}

BASE_LIMITS = [
    "Use only this evidence map; do not browse or rely on general model knowledge.",
    "Historical returns and filing reactions are observations, not forecasts.",
    "Do not provide a recommendation, price target, or directional prediction.",
    "If the evidence does not answer the question, say so explicitly.",
]

FUNDAMENTALS_LIMIT = (
    "Annual fundamentals are latest-restated research values, not a valuation model."
)
COMPANY_NEWS_LIMIT = (
    "Headlines are titles and publication dates only. They are not verified facts "
    "about the company and no article body was read."
)
MARKET_NEWS_LIMIT = (
    "Market headlines describe the broad market, not this company. Do not attribute "
    "a market development to this issuer or infer an effect on it."
)
SCOPE_BOUNDARY_LIMIT = (
    "This is a narrowed evidence scope chosen by the reader. If the question needs "
    "evidence outside it, say which scope would be required rather than guessing."
)


def evidence_scopes() -> list[dict[str, Any]]:
    """The selectable scopes, for the page's picker and the function's GET."""
    return [
        {
            "id": name,
            "label": SCOPE_LABELS[name]["en"],
            "label_zh": SCOPE_LABELS[name]["zh"],
            "description": SCOPE_DESCRIPTIONS[name]["en"],
            "description_zh": SCOPE_DESCRIPTIONS[name]["zh"],
            "sections": list(SCOPE_SECTIONS[name]),
        }
        for name in SCOPE_SECTIONS
    ]


def build_ask_evidence(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Reduce one public snapshot to a live-readable evidence map per scope."""
    ticker = str(snapshot["ticker"]).upper()
    benchmark = str(snapshot["benchmark"]).upper()
    profile = snapshot.get("profile") or {}
    performance = snapshot["performance"]
    filing = next(iter(snapshot.get("latest_filings") or []), None)

    # Each builder collects into its own citation map so a section can be left
    # out of a scope without its citations lingering in that scope's allow-list.
    profile_citations: dict[str, dict[str, str]] = {}
    profile_citation = "source:company-profile"
    profile_citations[profile_citation] = {
        "label": "SEC company record",
        "url": str(profile.get("source_url") or f"/{ticker.lower()}.html"),
        "section": "overview",
    }
    company_section = {
        "name": profile.get("display_name") or snapshot.get("company_name") or ticker,
        "category": profile.get("category"),
        "summary": profile.get("summary"),
        "citation": profile_citation,
    }

    performance_citations: dict[str, dict[str, str]] = {}
    performance_section = _performance_packet(
        ticker, benchmark, performance, performance_citations
    )

    filing_citations: dict[str, dict[str, str]] = {}
    filing_section = _filing_packet(filing, filing_citations)

    fundamentals_citations: dict[str, dict[str, str]] = {}
    fundamentals_section = _fundamentals_packet(
        snapshot.get("fundamentals"), ticker, fundamentals_citations
    )

    financial_citations: dict[str, dict[str, str]] = {}
    financial_section = financial_results_packet(
        snapshot.get("financial_results"), ticker, financial_citations
    )

    company_news_citations: dict[str, dict[str, str]] = {}
    company_news = _headline_packet(
        snapshot.get("headlines") or [], company_news_citations,
        source_type="company_news", section="company_news",
    )

    market_news_citations: dict[str, dict[str, str]] = {}
    market_news = _headline_packet(
        snapshot.get("market_headlines") or [], market_news_citations,
        source_type="market_news", section="market_news",
    )

    optional = {
        "company_headlines": (company_news, company_news_citations,
                              COMPANY_NEWS_LIMIT),
        "market_headlines": (market_news, market_news_citations,
                             MARKET_NEWS_LIMIT),
    }

    scopes: dict[str, Any] = {}
    for name, section_names in SCOPE_SECTIONS.items():
        citations: dict[str, dict[str, str]] = {
            **profile_citations, **performance_citations, **filing_citations, **financial_citations,
        }
        evidence: dict[str, Any] = {
            "schema_version": ASK_EVIDENCE_VERSION,
            "ticker": ticker,
            "as_of": snapshot["as_of"],
            "evidence_scope": name,
            "evidence_scope_label": SCOPE_LABELS[name]["en"],
            "company": company_section,
            "historical_performance": performance_section,
            "latest_filing": filing_section,
            "financial_results": financial_section,
        }
        limits = [*BASE_LIMITS, FINANCIAL_RESULTS_LIMIT]
        if fundamentals_section is not None:
            evidence["fundamentals"] = fundamentals_section
            citations.update(fundamentals_citations)
            limits.append(FUNDAMENTALS_LIMIT)

        for section_name in section_names:
            payload, section_citations, limit = optional[section_name]
            evidence[section_name] = payload
            # An empty section still declares itself. "No company headlines are
            # available" is a fact the model should state; silently omitting the
            # key invites it to answer from memory instead.
            citations.update(section_citations)
            if payload:
                limits.append(limit)
            else:
                limits.append(
                    f"No {section_name.replace('_', ' ')} are available in this "
                    "scope; say so rather than substituting general knowledge."
                )
        if name != "all":
            limits.append(SCOPE_BOUNDARY_LIMIT)
        evidence["interpretation_limits"] = limits

        canonical = json.dumps(evidence, sort_keys=True, ensure_ascii=False)
        scopes[name] = {
            "evidence": evidence,
            "citations": citations,
            "allowed_citations": sorted(citations),
            "allowed_number_literals": sorted({
                *NUMBER_LITERAL.findall(canonical),
                *localized_month_number_literals(evidence),
            }),
        }

    return {
        "schema_version": ASK_EVIDENCE_VERSION,
        "ticker": ticker,
        "default_scope": DEFAULT_SCOPE,
        "scopes": scopes,
    }


def _performance_packet(
    ticker: str,
    benchmark: str,
    performance: dict[str, Any],
    citations: dict[str, dict[str, str]],
) -> dict[str, Any]:
    page = f"/{ticker.lower()}.html#performance"
    metrics = {
        "asset_total_return": (
            "metric:asset.total_return",
            f"{performance['asset']['total_return']:+.1%}",
        ),
        "asset_annualized_return": (
            "metric:asset.cagr",
            f"{performance['asset']['cagr']:+.1%}",
        ),
        "asset_max_drawdown": (
            "metric:asset.max_drawdown",
            f"{performance['asset']['max_drawdown']:.1%}",
        ),
        "benchmark_total_return": (
            "metric:benchmark.total_return",
            f"{performance['benchmark']['total_return']:+.1%}",
        ),
        "relative_total_return": (
            "metric:relative_total_return",
            f"{performance['relative_total_return'] * 100:+.1f} percentage points",
        ),
        "observations": ("metric:observations", str(performance["observations"])),
    }
    packet: dict[str, Any] = {
        "asset": ticker,
        "benchmark": benchmark,
        "definition": (
            "Adjusted buy-and-hold history over the frozen snapshot period. Company and "
            "benchmark use common trading dates. Relative total return is company return "
            "minus benchmark return, in percentage points; it is not financial growth."
        ),
    }
    for name, (citation, value) in metrics.items():
        citations[citation] = {
            "label": name.replace("_", " ").title(),
            "url": page,
            "section": "history",
        }
        packet[name] = {"value": value, "citation": citation}
    return packet


def _filing_packet(
    filing: dict[str, Any] | None,
    citations: dict[str, dict[str, str]],
) -> dict[str, Any] | None:
    if not filing:
        return None
    source_url = str(filing["source_url"])
    source_citation = "source:latest-filing"
    citations[source_citation] = {
        "label": "Latest SEC filing",
        "url": source_url,
        "section": "filing",
    }
    passages = []
    for passage in (filing.get("passages") or [])[:6]:
        citation = str(passage["anchor"])
        citations[citation] = {
            "label": "SEC source passage",
            "url": str(passage.get("source_url") or source_url),
            "section": "filing",
        }
        passages.append(
            {
                "text": passage["text"],
                "citation": citation,
            }
        )
    packet: dict[str, Any] = {
        "accession": filing["accession"],
        "form": filing["form"],
        "accepted_at": filing["accepted_at"],
        "items": filing.get("items") or [],
        "source_citation": source_citation,
        "passages": passages,
    }
    comparison = filing.get("comparison")
    if comparison:
        count_citation = "metric:filing.comparison_counts"
        citations[count_citation] = {
            "label": "Filing wording comparison",
            "url": source_url,
            "section": "filing",
        }
        packet["comparison"] = {
            "prior_accepted_at": comparison.get("prior_accepted_at"),
            "counts": {
                **(comparison.get("counts") or {}),
                "citation": count_citation,
            },
        }
    reaction = filing.get("reaction")
    if reaction:
        reaction_fields = {
            "asset_open_to_close": f"{reaction['asset_open_to_close']:+.1%}",
            "benchmark_open_to_close": f"{reaction['benchmark_open_to_close']:+.1%}",
            "benchmark_adjusted_move": f"{reaction['benchmark_adjusted_move']:+.1%}",
            "prior_sample_size": str(reaction["prior_sample_size"]),
        }
        if reaction.get("magnitude_percentile") is not None:
            reaction_fields["historical_magnitude_percentile"] = (
                f"{reaction['magnitude_percentile']:.0%}"
            )
        packet["reaction"] = {
            "session": reaction["session"],
            "definition": (
                "First eligible session open-to-close issuer return less benchmark "
                "open-to-close return; this does not establish causality."
            ),
        }
        for name, value in reaction_fields.items():
            citation = f"metric:filing.{name}"
            citations[citation] = {
                "label": name.replace("_", " ").title(),
                "url": source_url,
                "section": "filing",
            }
            packet["reaction"][name] = {"value": value, "citation": citation}
    return packet


def _headline_packet(
    headlines: list[dict[str, Any]],
    citations: dict[str, dict[str, str]],
    *,
    source_type: str,
    section: str,
) -> list[dict[str, Any]]:
    packet = []
    rows = [
        headline
        for headline in headlines
        if headline.get("source_type") == source_type
    ][:3]
    for headline in rows:
        citation = str(headline["citation"])
        citations[citation] = {
            "label": str(headline["publisher"]),
            "url": str(headline["url"]),
            "section": section,
        }
        packet.append(
            {
                "headline": headline["headline"],
                "publisher": headline["publisher"],
                "published_at": headline["published_at"],
                "citation": citation,
            }
        )
    return packet


def _fundamentals_packet(
    fundamentals: dict[str, Any] | None,
    ticker: str,
    citations: dict[str, dict[str, str]],
) -> dict[str, Any] | None:
    if not fundamentals or fundamentals.get("status") != "available":
        return None
    page = f"/{ticker.lower()}.html#brief"
    series_basis = str(fundamentals.get("series_basis") or "latest_restated")
    packet: dict[str, Any] = {
        "status": fundamentals["status"],
        "series_basis": series_basis,
        "requested_years": fundamentals.get("requested_years"),
        "knowledge_at": fundamentals.get("knowledge_at"),
        "annual_trends": [],
        "coverage_warnings": list(fundamentals.get("warnings") or [])[:6],
    }
    wanted = (
        "revenue",
        "gross_margin",
        "operating_margin",
        "fcf_per_share",
        "diluted_shares",
        "free_cash_flow",
        "ocf_to_net_income",
        "diluted_share_change",
    )
    reported = {
        series["metric_id"]: series
        for series in fundamentals.get("reported_series") or []
    }
    derived = {
        series["metric_id"]: series
        for series in fundamentals.get("derived_series") or []
    }
    source_citations = {
        observation["citation"]["citation_id"]: observation["citation"]
        for series in fundamentals.get("reported_series") or []
        for observation in series.get("observations") or []
        if observation.get("citation", {}).get("citation_id")
    }
    for metric_id in wanted:
        series = reported.get(metric_id) or derived.get(metric_id)
        if not series:
            continue
        observations = []
        for item in series.get("observations") or []:
            if item.get("status") not in (None, "available"):
                continue
            if item.get("value") is None:
                continue
            if "share_basis_noncomparable" in (item.get("quality_flags") or []):
                continue
            citation = f"metric:fundamentals.{metric_id}.{item['fiscal_year']}"
            component_ids = [
                value
                for value in (item.get("components") or {}).values()
                if value in source_citations
            ]
            direct = item.get("citation") or {}
            direct_citation_id = direct.get("citation_id")
            source_records = [direct] if direct.get("source_url") else [
                source_citations[value] for value in component_ids
            ]
            source_urls = list(
                dict.fromkeys(
                    str(record.get("source_url"))
                    for record in source_records
                    if record.get("source_url")
                )
            )
            for source_record in source_records:
                source_id = source_record.get("citation_id")
                source_url = source_record.get("source_url")
                if not source_id or not source_url:
                    continue
                citations.setdefault(
                    str(source_id),
                    {
                        "label": (
                            f"SEC source for {series.get('label', metric_id)} "
                            f"FY{item['fiscal_year']}"
                        ),
                        "url": str(source_url),
                        "section": "fundamentals",
                    },
                )
            citations[citation] = {
                "label": f"{series.get('label', metric_id)} FY{item['fiscal_year']}",
                "url": source_urls[0] if source_urls else page,
                "section": "fundamentals",
            }
            observations.append(
                {
                    "fiscal_year": item["fiscal_year"],
                    "period_end": item.get("period_end"),
                    "value": item["value"],
                    "display_value": _format_evidence_value(
                        float(item["value"]),
                        str(
                            item.get("unit")
                            or series.get("unit")
                            or series.get("expected_unit")
                            or ""
                        ),
                    ),
                    "unit": item.get("unit")
                    or series.get("unit")
                    or series.get("expected_unit"),
                    "citation": citation,
                    "source_citations": list(
                        dict.fromkeys(
                            component_ids
                            or ([direct_citation_id] if direct_citation_id else [])
                        )
                    ),
                    "formula_version": item.get("formula_version"),
                }
            )
        if not observations:
            continue
        packet["annual_trends"].append(
            {
                "metric_id": metric_id,
                "label": series.get("label", metric_id),
                "definition": series.get("definition"),
                "coverage_status": (
                    "complete"
                    if len(observations) >= int(packet.get("requested_years") or 10)
                    else "partial"
                ),
                "observations": observations[-10:],
            }
        )
    if not packet["annual_trends"]:
        return None
    return packet


def _format_evidence_value(value: float, unit: str) -> str:
    """Return a compact literal the model may quote without recalculating."""
    if unit == "ratio":
        return f"{value * 100:.1f}%"
    if unit in {"USD", "USD/shares"}:
        scale = abs(value)
        if scale >= 1_000_000_000:
            return f"${value / 1_000_000_000:.1f}B"
        if scale >= 1_000_000:
            return f"${value / 1_000_000:.1f}M"
        if unit == "USD/shares":
            return f"${value:,.2f}"
        return f"${value:,.0f}"
    if unit == "shares":
        scale = abs(value)
        if scale >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f}B"
        if scale >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        return f"{value:,.0f}"
    return f"{value:,.4g}"
