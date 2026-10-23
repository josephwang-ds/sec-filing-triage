# Full-width punctuation is intentional in the user-facing Chinese interface copy.
# ruff: noqa: RUF001
"""A self-contained Company Lens page backed only by the snapshot contract."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from company_lens.contracts import (
    Citation,
    CompanySnapshot,
    EvidenceScopeSummary,
    FilingBrief,
    FilingChange,
    FilingEntity,
    FilingTimelinePoint,
    HeadlineBrief,
)
from company_lens.profiles import DEMO_PROFILES
from company_lens.web.financials import financial_results_section

DEFAULT_TICKERS = ("AAPL", "MSFT", "NVDA")


def render_company_page(
    snapshot: CompanySnapshot,
    output: str | Path,
    *,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
) -> Path:
    """Write one offline-capable HTML page from a versioned snapshot."""
    del tickers  # retained for callers built against the pre-v1.4 renderer
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_document(snapshot), encoding="utf-8")
    return output


def render_index(
    output: str | Path,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    *,
    companies: list[dict[str, str]] | None = None,
    featured_tickers: tuple[str, ...] = DEFAULT_TICKERS,
) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    companies = companies or [
        {
            "ticker": ticker,
            "name": DEMO_PROFILES.get(ticker, {}).get("display_name", ticker),
        }
        for ticker in tickers
    ]
    featured = [
        company for company in companies if company["ticker"] in featured_tickers
    ] or companies[:3]
    links = "".join(
        f'<a class="company-link" href="{html.escape(company["ticker"].lower())}.html">'
        f'<span>{html.escape(company["ticker"])}</span>'
        f'<strong>{html.escape(company["name"])}</strong>'
        f'<small data-index-i18n="card.open">Open company lens →</small></a>'
        for company in featured
    )
    options = "".join(
        f'<option value="{html.escape(company["ticker"])}">'
        f'{html.escape(company["name"])}</option>'
        for company in companies
    )
    search_payload = json.dumps(companies, ensure_ascii=False).replace("</", "<\\/")
    output.write_text(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Company Lens · Evidence-backed company research</title>
<meta name="description" content="Explore company performance, SEC disclosures and source-backed explanations. Review the evidence and research methods behind every company lens.">
<meta name="theme-color" content="#183c35"><style>{_index_css()}</style></head>
<body><main><header class="index-topbar"><a class="index-brand" href="index.html">
<span>CL</span><strong>Company Lens</strong></a><div>
<a class="topbar-link" href="overview.html" data-index-i18n="nav.what">What this is</a>
<a class="topbar-link" href="research.html" data-index-i18n="nav.research">How this is audited</a>
<small data-index-i18n="nav.scope">{len(companies)}-company evidence universe</small>
<button class="index-language-toggle" id="index-language-toggle" type="button"
aria-label="切换为中文" aria-pressed="false">中文</button></div></header>
<div class="index-hero">
<p class="eyebrow" data-index-i18n="hero.eyebrow">SOURCE-BACKED COMPANY INTELLIGENCE</p>
<h1><span data-index-i18n="hero.title">Understand the company.</span><br><em data-index-i18n="hero.emphasis">Keep the evidence.</em></h1>
<p class="lede" data-index-i18n="hero.lede">Historical return and risk, recent SEC disclosures, and a bounded
AI explanation with citations. No price prediction. No investment recommendation.</p>
<form id="company-search" class="company-search">
<label for="ticker-search" data-index-i18n="search.label">Search {len(companies)} locally available companies</label>
<div class="search-row"><input id="ticker-search" name="ticker" list="supported-companies"
placeholder="Try AAPL or Apple" data-index-i18n-placeholder="search.placeholder"
autocomplete="off" spellcheck="false" required>
<datalist id="supported-companies">{options}</datalist>
<button type="submit" data-index-i18n="search.submit">Open lens</button></div>
<p id="search-status" class="search-status" aria-live="polite"
data-status-key="search.hint">Type an exact ticker or
company name from the current local universe.</p></form></div>
    <p class="featured-label" data-index-i18n="featured">Featured examples</p><div class="companies">{links}</div>
    <section class="method-note" id="method">
    <p class="eyebrow" data-index-i18n="method.eyebrow">HOW TO READ A LENS</p>
    <h2 data-index-i18n="method.title">Company first. Evidence second.</h2>
    <p data-index-i18n="method.intro">Every page follows one order: historical picture, latest SEC disclosure, then
    company-specific context. Broad market headlines and implementation details stay off
    the company page so they cannot be mistaken for company evidence.</p>
    <ol><li><span>01</span><strong data-index-i18n="method.history">History</strong><small data-index-i18n="method.history_copy">Price and risk versus SPY</small></li>
    <li><span>02</span><strong data-index-i18n="method.disclosure">Disclosure</strong><small data-index-i18n="method.disclosure_copy">What the latest 8-K actually says</small></li>
    <li><span>03</span><strong data-index-i18n="method.boundary">Boundary</strong><small data-index-i18n="method.boundary_copy">Citations, limitations, no forecast</small></li></ol>
    <details class="method-tech-note"><summary data-index-i18n="method.expand">Under the hood</summary>
    <p class="method-tech" data-index-i18n="method.tech"><strong>Under the hood:</strong> point-in-time SEC ingestion,
    return and risk calculations, deterministic NLP change filtering, and an optional
    source-bounded LLM explanation layer.</p></details>
    <div class="method-links">
    <a href="overview.html"><strong data-index-i18n="method.overview">What this project is</strong>
    <small data-index-i18n="method.overview_copy">The problem, the result, and the mistake that made it look twice as good &mdash; in plain words</small></a>
    <a href="research.html"><strong data-index-i18n="method.research">How the ranking was audited</strong>
    <small data-index-i18n="method.research_copy">The leakage ladder, the intervals, and what the label cannot claim</small></a>
    </div></section>
    <details class="company-directory" id="directory"><summary><div>
    <p class="eyebrow" data-index-i18n="directory.eyebrow">LOCAL DIRECTORY</p>
    <h2 data-index-i18n="directory.title">Explore the company directory</h2></div>
    <span data-index-i18n="directory.expand">Browse all companies</span></summary>
    <div class="directory-body"><div class="directory-toolbar">
    <p id="directory-status" aria-live="polite"></p><div>
    <button id="directory-previous" type="button" data-index-i18n="directory.previous">Previous</button>
    <button id="directory-next" type="button" data-index-i18n="directory.next">Next</button>
    </div></div><div class="directory-grid" id="directory-grid"></div></div></details>
    <p class="foot" data-index-i18n="footer">Cached real-data demonstration ·
SEC EDGAR + vendor-adjusted daily prices</p></main>
<script type="application/json" id="company-data">{search_payload}</script>
<script>{_index_script()}</script></body></html>""",
        encoding="utf-8",
    )
    return output


def render_unsupported(
    output: str | Path,
    *,
    company_count: int,
    featured_tickers: tuple[str, ...] = DEFAULT_TICKERS,
) -> Path:
    """Write a friendly static-host 404 page that preserves the scope boundary."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    featured = ", ".join(featured_tickers)
    output.write_text(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Company not cached · Company Lens</title><style>{_index_css()}</style></head>
<body><main><p class="eyebrow">CACHED DEMO BOUNDARY</p>
<h1>This company is<br><em>not cached yet.</em></h1>
<p class="lede">This ticker is not in the current local {company_count}-company universe.
Featured examples are {html.escape(featured)}. The page will not fabricate a profile
or silently fetch a different evidence set.</p>
<p><a class="return-link" href="index.html">← Return to supported companies</a></p>
</main></body></html>""",
        encoding="utf-8",
    )
    return output


def _document(snapshot: CompanySnapshot) -> str:
    company_name = snapshot.profile.get("display_name") or snapshot.company_name
    payload = json.dumps(snapshot.period_options, ensure_ascii=False).replace("</", "<\\/")
    default_period = _default_period(snapshot)
    filings = "".join(
        _filing_card(filing, index, snapshot.benchmark)
        for index, filing in enumerate(snapshot.latest_filings)
    ) or '<p class="empty">No local 8-K filings are available for this company.</p>'
    period_buttons = "".join(
        f'<button class="period-button" data-period="{label}" type="button">{label}</button>'
        for label in snapshot.period_options
    )
    benchmark_buttons = _benchmark_buttons(snapshot)
    comparisons = json.dumps(snapshot.benchmark_comparisons, ensure_ascii=False).replace(
        "</", "<\\/"
    )
    brief = _brief(snapshot)
    intro_key = "brief.intro"
    intro = ("Start with the latest disclosure, then the historical picture. "
             "Every number links to its source.")
    evidence_context = _evidence_context(snapshot.evidence_scope, snapshot.headlines)
    context_nav = (
        '<a href="#context" data-i18n="nav.company_news">Company news</a>'
        if evidence_context
        else ""
    )
    latest_filing_date = (
        snapshot.latest_filings[0].accepted_at[:10] if snapshot.latest_filings else "Unavailable"
    )
    refresh = snapshot.provenance.get("filing_refresh") or {}
    source_checked_at = refresh.get("checked_at") or snapshot.provenance.get("written_at")
    if refresh.get("checked_at"):
        source_check_key = "filings.sec_checked"
        source_check_prefix = "SEC checked"
    elif source_checked_at:
        source_check_key = "filings.sec_collected"
        source_check_prefix = "SEC cache collected"
    else:
        source_check_key = "filings.sec_unavailable"
        source_check_prefix = "SEC cache time unavailable"
    source_check_date = str(source_checked_at)[:10] if source_checked_at else ""
    # Stated in the footer rather than as a banner over the page. It is true and
    # it belongs on the page; it is not the first thing a reader needs.
    universe = snapshot.provenance.get("universe") or {}
    universe_note = ("<span data-i18n=\"footer.universe\">Universe: a convenience sample of current large caps, "
                     "not a point-in-time index</span>"
                     if universe.get("survivorship_controlled") is False else "")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Source-backed company intelligence for {html.escape(company_name)}">
<title>{html.escape(snapshot.ticker)} · Company Lens</title>
<style>{_css()}</style>
</head>
<body>
<header class="topbar">
  <a class="brand" href="index.html"><span class="brand-mark">CL</span><span>Company Lens</span></a>
  <nav class="company-nav" aria-label="Company navigation">
    <a href="index.html" class="company-search-link" data-i18n="nav.find">Find a company</a>
    <span class="current-symbol" aria-current="page">{html.escape(snapshot.ticker)}</span>
    <a href="#earnings" class="site-link" data-i18n="nav.earnings">Financial results</a>
    <a href="overview.html" class="site-link" data-i18n="nav.what">What this is</a>
    <a href="research.html" class="site-link" data-i18n="nav.research">How this is audited</a>
  </nav>
  <nav class="section-nav" aria-label="Page storyline">
        <a href="#brief" data-i18n="nav.overview">Overview</a>
        <a href="#performance" data-i18n="nav.history">History</a>
        <a href="#filings" data-i18n="nav.filings">Filings</a>
        <a href="#ask" data-i18n="nav.ask">Ask AI</a>{context_nav}
  </nav>
  <span class="trust-label" data-i18n="nav.trust">Evidence, not prediction</span>
  <button class="language-toggle" id="language-toggle" type="button"
  aria-label="切换为中文" aria-pressed="false">中文</button>
</header>

<main>
  <section class="company-hero">
    <div>
      <p class="eyebrow" data-i18n="hero.eyebrow">COMPANY OVERVIEW · SOURCE-BACKED</p>
      <div class="company-title"><h1>{html.escape(company_name)}</h1>
      <span>{html.escape(snapshot.ticker)}</span></div>
      <p class="profile-category" data-i18n="profile.category"
      data-i18n-en="{html.escape(str(snapshot.profile.get('category', 'Public company')))}"
      data-i18n-zh="{html.escape(str(snapshot.profile.get('category_zh') or snapshot.profile.get('category', 'Public company')))}">{html.escape(str(snapshot.profile.get('category', 'Public company')))}</p>
      <p class="hero-copy" data-i18n="profile.summary"
      data-i18n-en="{html.escape(str(snapshot.profile.get('summary', 'Business profile unavailable.')))}"
      data-i18n-zh="{html.escape(str(snapshot.profile.get('summary_zh') or snapshot.profile.get('summary', 'Business profile unavailable.')))}">{html.escape(str(snapshot.profile.get('summary', 'Business profile unavailable.')))}</p>
      {_profile_meta(snapshot.profile)}
        </div>
    <div class="market-observation">
      <span data-i18n="hero.latest_close">Latest adjusted close</span>
      <strong>{_money(snapshot.market['latest_adjusted_close'])}</strong>
      <small><span data-i18n="hero.observed">Observed</span> {html.escape(snapshot.market['price_date'])}</small>
    </div>
  </section>

  <nav class="page-nav" id="page-nav" aria-label="On this page">
    <div><p class="eyebrow" data-i18n="workspace.eyebrow">ON THIS PAGE</p>
    <strong data-i18n="workspace.title">Read the brief, then verify below.</strong></div>
    <div class="page-nav-links">{_nav_links(snapshot)}</div>
  </nav>

  <section class="brief-section" id="brief" aria-labelledby="brief-title">
    <div class="section-heading">
          <div><p class="eyebrow" data-i18n="brief.eyebrow">ONE-MINUTE BRIEF</p>
          <h2 id="brief-title" data-i18n="brief.title">What matters on this page</h2></div>
      <span class="mode-badge" data-explanation-mode="{html.escape(str(snapshot.explanation.get('mode') or 'unavailable'))}">{_mode_label(snapshot.explanation.get('mode'))}</span>
    </div>
        <p class="brief-intro" data-i18n="{intro_key}">{intro}</p>
        <div class="brief-grid">{brief}</div>
      </section>

  {financial_results_section(snapshot.financial_results)}

  <section class="performance-section" id="performance" aria-labelledby="performance-title"
  data-benchmark-scope="history">
    <div class="section-heading performance-heading">
      <div><p class="eyebrow" data-i18n="performance.eyebrow">HISTORICAL INVESTMENT PICTURE</p>
      <h2 id="performance-title" data-i18n="performance.title">What happened to $10,000?</h2></div>
      <div class="history-controls">
      {benchmark_buttons}
      <div class="period-control" aria-label="Historical period">{period_buttons}</div>
      </div>
    </div>
    <p class="section-intro" data-i18n="performance.intro">Adjusted buy-and-hold history versus {html.escape(snapshot.benchmark)}
    over the exact same dates. Historical context, not expected return.</p>
    <p class="section-intro" id="benchmark-definition">{html.escape(_benchmark_definition(snapshot.benchmark))}</p>
    <p class="benchmark-note" id="benchmark-note" aria-live="polite"></p>
    <details class="diagnostics-disclosure"><summary data-i18n-en="Return definition and comparison" data-i18n-zh="回报口径与比较方法">Return definition and comparison</summary>
      <p data-i18n-en="Cumulative return = ending adjusted close / starting adjusted close − 1; it is not an annual or quarterly financial growth rate. Company and selected ETF use only their common trading dates, shown above the chart. Return gap subtracts the ETF return from company return, in percentage points. SPY provides broad US large-cap market context; QQQ provides Nasdaq-100 context, not a matched industry peer portfolio."
      data-i18n-zh="累计回报 = 期末复权收盘价 ÷ 期初复权收盘价 − 1；不是年度或季度财务增速。公司与所选 ETF 仅使用双方共同交易日，具体日期显示在图表上方。回报差为公司回报减去 ETF 回报，单位为百分点。SPY 提供美国大盘背景；QQQ 提供纳斯达克 100 背景，不代表同行业可比公司组合。">Cumulative return = ending adjusted close / starting adjusted close − 1; company and ETF use common trading dates.</p>
      <p data-i18n-en="Prices are vendor-adjusted; dividends are included only when supplied by that vendor. USD illustration, before fees and taxes. No currency conversion or valuation/earnings comparison is implied."
      data-i18n-zh="价格采用供应商复权数据；仅当供应商数据包含分红时才反映分红。图中按美元展示，未扣费用与税费；不涉及汇率换算，也不代表估值或财务业绩比较。">Vendor-adjusted prices; dividends only when supplied by the vendor; USD, before fees and taxes.</p>
    </details>
    <div class="performance-layout">
      <div class="chart-panel">
        <div class="chart-legend">
          <span><i class="line asset"></i>{html.escape(snapshot.ticker)}</span>
          <span><i class="line benchmark"></i><span id="legend-benchmark">{html.escape(snapshot.benchmark)}</span></span>
          <span id="chart-range"></span>
        </div>
        <svg id="growth-chart" viewBox="0 0 920 360" role="img"
             aria-label="Growth of ten thousand dollars compared with benchmark">
          <g id="chart-grid"></g><path id="benchmark-path"></path><path id="asset-path"></path>
          <g id="chart-labels"></g><line id="hover-line" x1="0" x2="0" y1="24" y2="314"></line>
          <circle id="asset-point" r="5"></circle><circle id="benchmark-point" r="5"></circle>
          <rect class="chart-hit" x="58" y="20" width="838" height="296"></rect>
        </svg>
        <div id="chart-tooltip" class="chart-tooltip" aria-live="polite"></div>
      </div>
      <aside class="ending-card">
        <span data-i18n="performance.ending_value">Ending value</span><strong id="ending-value"></strong>
        <small id="history-return-comparison"></small>
        <small id="relative-copy"></small>
        <div class="mini-comparison"><span id="benchmark-ending-label">{html.escape(snapshot.benchmark)} ending value</span>
        <b id="benchmark-ending"></b></div>
      </aside>
    </div>
        <details class="diagnostics-disclosure"><summary data-i18n="performance.more_risk">More risk metrics</summary>
        <div class="metric-grid">
          {_metric("Annualized return", "cagr", "Compound annual growth rate; historical, not forecast.", "metric.return")}
      {_metric("Annualized volatility", "volatility", "Standard deviation of daily returns, annualized.", "metric.volatility")}
      {_metric(f"Beta vs {snapshot.benchmark}", "beta", "Sensitivity to benchmark daily returns; 1.0 moves roughly with the benchmark.", "metric.beta")}
      {_metric(f"Correlation vs {snapshot.benchmark}", "correlation", "How closely daily returns moved together; ranges from -1 to +1.", "metric.correlation")}
      {_metric("Current drawdown", "current-drawdown", "Distance below the highest adjusted value in the period.", "metric.current_drawdown")}
      {_metric("Worst day", "worst-day", "Largest single-session adjusted-price decline in the selected period.", "metric.worst_day")}
        </div></details>
        <div class="risk-note" id="risk-note"></div>
  </section>

  <section class="filings-section" id="filings" aria-labelledby="filings-title">
    <div class="section-heading">
      <div><p class="eyebrow" data-i18n="filings.eyebrow">FILING INTELLIGENCE</p>
      <h2 id="filings-title" data-i18n="filings.title">Recent 8-K disclosures</h2></div>
      <div class="freshness-group"><span class="freshness"
      data-freshness-key="filings.latest_accepted"
      data-freshness-date="{html.escape(latest_filing_date)}">Latest filing accepted {html.escape(latest_filing_date)}</span>
      <span class="freshness" data-freshness-key="{source_check_key}"
      data-freshness-date="{html.escape(source_check_date)}">{source_check_prefix}{' ' if source_check_date else ''}{html.escape(source_check_date)}</span></div>
    </div>
        <p class="section-intro" data-i18n="filings.intro">The newest filing stays open. Read what arrived, what the
        next eligible session did, and whether the wording changed in a substantive way.</p>
        <div class="filing-list">{filings}</div>
  </section>

  {_disclosure_signal(snapshot)}
  {_volatility_forecast(snapshot)}
  {_ask_section()}

  {evidence_context}

    </main>

    <footer><div><strong>Company Lens</strong><span data-i18n="footer.tagline">Understand the evidence before forming a view.</span>
    <a href="index.html#method" data-i18n="footer.how">How to read this lens</a></div>
<div class="footer-meta">{universe_note}<span><span data-i18n="footer.snapshot">Snapshot</span> v{html.escape(snapshot.schema_version)}</span>
<span><span data-i18n="footer.market">Market through</span> {html.escape(snapshot.as_of)}</span><span data-i18n="footer.sources">SEC + adjusted daily prices</span></div></footer>

<script type="application/json" id="period-data">{payload}</script>
<script type="application/json" id="benchmark-data">{comparisons}</script>
<script>{_script(default_period, snapshot.ticker, snapshot.benchmark)}</script>
</body></html>"""



def _nav_links(snapshot: CompanySnapshot) -> str:
    """The section list, numbered from what the page actually contains.

    Built rather than written out because three of these sections are
    conditional -- the signal card, the volatility band and company news each
    appear only when their data does -- and a hand-numbered list either skips a
    number or points at a section that is not there.
    """
    entries = [("#brief", "nav.overview", "Overview"),
               ("#performance", "nav.history", "History"),
               ("#filings", "nav.filings", "Filings")]
    if snapshot.disclosure_signal:
        entries.append(("#signal", "nav.signal", "This filing"))
    if snapshot.volatility_forecast:
        entries.append(("#volatility", "nav.volatility", "Expected range"))
    entries.append(("#ask", "nav.ask", "Ask AI"))
    if snapshot.evidence_scope:
        entries.append(("#context", "nav.company_news", "Company news"))
    return "".join(
        f'<a href="{href}"><span>{i:02d}</span>'
        f'<b data-i18n="{key}">{label}</b></a>'
        for i, (href, key, label) in enumerate(entries, start=1))


def _localized_reason(reason: str) -> str:
    """Translate generated model explanations without changing their evidence."""
    exact = {
        "evidence or freshness checks did not pass": "证据或时效性检查未通过",
        "too few earlier filings from this issuer to say what is normal": "该公司的历史披露不足，尚无法判断常态",
        "elevated model probability without a confirming signal": "模型概率偏高，但缺少可核验的佐证信号",
        "consistent with this issuer's usual disclosures": "与该公司以往的常规披露一致",
        "the most unusual language in this issuer's filing history": "措辞异常度为该公司披露历史最高",
        "the heaviest pre-filing volume in its own history": "披露前成交量为该公司历史最高",
        "the longest filing this issuer has made": "文件长度为该公司披露历史最高",
    }
    translated = exact.get(reason)
    if translated is None:
        patterns = (
            (r"more unusual language than ([0-9]+%) of this issuer's earlier filings", "措辞比该公司此前 {} 的披露更异常"),
            (r"pre-filing volume above ([0-9]+%) of its own history", "披露前成交量高于该公司历史中 {} 的观测"),
            (r"longer than ([0-9]+%) of its own filings", "文件长度超过该公司此前 {} 的披露"),
        )
        for pattern, template in patterns:
            match = re.fullmatch(pattern, reason)
            if match:
                translated = template.format(match.group(1))
                break
    return (f'<span data-i18n-en="{html.escape(reason)}" '
            f'data-i18n-zh="{html.escape(translated or reason)}">{html.escape(reason)}</span>')


def _disclosure_signal(snapshot: CompanySnapshot) -> str:
    """The latest filing measured against this issuer's own history.

    Leads with the decision, because that is what a reader came for, and puts
    every qualifier the decision rests on in the same block rather than a
    footnote: how many of this issuer's earlier filings the baseline was built
    from, how often this issuer clears its own bar anyway, and the boundary that
    magnitude is not direction.

    Absent data renders nothing at all. A card that says "unknown" in four slots
    occupies the same space as a real answer and reads like a broken feature.
    """
    signal = snapshot.disclosure_signal
    if not signal:
        return ""

    state = str(signal.get("state", "insufficient_history"))
    words = {
        "read_now": ("Read now", "urgent"),
        "monitor": ("Monitor", "watch"),
        "routine": ("Routine", "calm"),
        "insufficient_history": ("Not enough history", "muted"),
        "withheld": ("Withheld", "muted"),
    }
    label, tone = words.get(state, ("Not enough history", "muted"))

    probability = signal.get("probability")
    base = signal.get("issuer_base_rate")
    depth = int(signal.get("eligible_history") or 0)

    stats = ""
    if probability is not None:
        stats = (
            f'<div class="signal-stats">'
            f'<div><b>{probability:.0%}</b><span data-i18n="signal.probability">'
            f'chance of an unusually large reaction</span></div>'
            f'<div><b>{base:.0%}</b><span data-i18n="signal.base">'
            f'how often this issuer clears its own bar</span></div>'
            f'<div><b>{depth}</b><span data-i18n="signal.history">'
            f'earlier filings behind the comparison</span></div>'
            f'</div>'
        )

    reasons = "".join(f"<li>{_localized_reason(str(reason))}</li>"
                      for reason in signal.get("reasons", []))
    points = json.dumps(signal.get("points", []))
    model = signal.get("model", {})
    footer = html.escape(
        f"{model.get('estimator', 'model')} · calibration "
        f"{model.get('calibration', 'n/a')} · evaluated through "
        f"{model.get('evaluated_through', 'n/a')}")

    return f"""<section class="signal-section" id="signal">
    <div class="section-heading"><div>
    <p class="eyebrow" data-i18n="signal.eyebrow">THIS FILING VS ITS OWN HISTORY</p>
    <h2 data-i18n="signal.title">Is this unusual for this company?</h2></div>
    <span class="signal-badge {tone}" data-i18n="signal.state.{state}">{label}</span></div>
    <p class="section-intro" data-i18n="signal.intro">Every number here compares this
    filing with earlier filings from the same issuer. Nothing compares it with other
    companies, and nothing here is a view on price direction.</p>
    {stats}
    <div class="signal-grid">
      <div class="signal-why">
        <h3 data-i18n="signal.why">Why</h3>
        <ul>{reasons}</ul>
        <p class="signal-boundary" data-i18n="signal.boundary">This estimates how
        large a reaction may be, not which way it goes. It is a reading priority,
        not investment advice.</p>
      </div>
      <figure class="signal-chart">
        <svg viewBox="0 0 320 210" role="img"
             data-aria-zh="该公司历次披露的措辞异常度与实际市场反应幅度对比" aria-label="Each earlier filing from this issuer, plotted by how unusual its language was against how large its reaction turned out to be.">
          <g id="signal-plot"></g>
        </svg>
        <figcaption>
          <span data-i18n="signal.chart_x">Unusual language &rarr;</span>
          <span data-i18n="signal.chart_y">&uarr; Reaction size</span>
        </figcaption>
      </figure>
    </div>
    <p class="signal-footer" data-i18n-en="{footer}"
    data-i18n-zh="{html.escape(str(model.get('estimator', 'model')))} · 校准方法 {html.escape(str(model.get('calibration', 'n/a')))} · 评估截至 {html.escape(str(model.get('evaluated_through', 'n/a')))}">{footer}</p>
    <script type="application/json" id="signal-points">{points}</script>
    </section>"""


def _volatility_forecast(snapshot: CompanySnapshot) -> str:
    """The next twenty sessions as a range, next to what this issuer usually does.

    A band on its own is unreadable -- 25% is calm for one issuer and alarming for
    another -- so the issuer's own usual level sits beside it and the plain-word
    state is a comparison of the two, not a threshold on the number.

    The bar itself is the whole chart: the issuer's usual level is a tick on it,
    so "wider than usual" is something a reader sees rather than something the
    card asserts.
    """
    forecast = snapshot.volatility_forecast
    if not forecast or forecast.get("median") is None:
        return ""

    median = float(forecast["median"])
    low, high = float(forecast["band_low"]), float(forecast["band_high"])
    usual = float(forecast.get("issuer_median") or 0.0)
    state = str(forecast.get("state", "typical for this issuer"))
    tone = {"elevated": "urgent", "slightly elevated": "watch",
            "unusually calm": "calm"}.get(state, "muted")
    # Sentence case, matching what the dictionary swaps in: a badge that changed
    # capitalisation when the language toggle was pressed would look like a bug.
    label = state[:1].upper() + state[1:]

    # The bar spans a fixed range rather than the band's own, so two companies'
    # cards are comparable at a glance and a narrow band looks narrow.
    span = max(high, usual, 0.6) * 1.05
    def at(value: float) -> float:
        return max(0.0, min(100.0, 100.0 * value / span))

    coverage = forecast.get("coverage_80")
    footnote = (f"the 80% band held {float(coverage):.0%} of outcomes out of sample"
                if coverage is not None else "")

    names = {"har": "trailing-volatility regression",
             "climatology": "this issuer\u2019s own history",
             "random_walk": "today carried forward",
             "chronos": "Chronos-2"}
    forecaster = names.get(str(forecast.get("forecaster", "")),
                           str(forecast.get("forecaster", "")))

    forecaster_zh = {"har": "历史波动率回归", "climatology": "该公司自身历史",
                     "random_walk": "沿用当前波动率", "chronos": "Chronos-2"}.get(
                         str(forecast.get("forecaster", "")), forecaster)
    footnote_zh = (f"样本外有 {float(coverage):.0%} 的结果落在 80% 区间内"
                   if coverage is not None else "")

    return f"""<section class="vol-section" id="volatility">
    <div class="section-heading"><div>
    <p class="eyebrow" data-i18n="vol.eyebrow" data-i18n-count="{int(forecast.get('horizon_sessions', 20))}">THE NEXT {int(forecast.get('horizon_sessions', 20))} SESSIONS</p>
    <h2 data-i18n="vol.title">How wide a range to expect</h2></div>
    <span class="signal-badge {tone}" data-i18n="vol.state.{state.replace(' ', '_')}">{html.escape(label)}</span></div>
    <p class="section-intro" data-i18n="vol.intro">How much this stock is expected to
    move over the next month, as a range rather than a number. It says nothing about
    which way &mdash; a wide range is as consistent with good news as with bad.</p>
    <div class="vol-bar" role="img"
         data-aria-zh="预期年化波动率区间为 {low:.0%} 至 {high:.0%}，最可能为 {median:.0%}，该公司常态为 {usual:.0%}。" aria-label="Expected annualised volatility between {low:.0%} and {high:.0%}, most likely {median:.0%}, against this issuer's usual {usual:.0%}.">
      <div class="vol-track">
        <div class="vol-band" style="left:{at(low):.1f}%;width:{at(high) - at(low):.1f}%"></div>
        <div class="vol-median" style="left:{at(median):.1f}%"></div>
        <div class="vol-usual" style="left:{at(usual):.1f}%"></div>
      </div>
      <div class="vol-scale"><span>0%</span><span>{span:.0%}</span></div>
    </div>
    <div class="signal-stats">
      <div><b>{median:.0%}</b><span data-i18n="vol.median">most likely, annualised</span></div>
      <div><b>{low:.0%}&ndash;{high:.0%}</b><span data-i18n="vol.band">80% of the time, in this range</span></div>
      <div><b>{usual:.0%}</b><span data-i18n="vol.usual">this issuer&rsquo;s usual level</span></div>
    </div>
    <p class="signal-footer" data-i18n-en="{html.escape(forecaster)} · as of {html.escape(str(forecast.get('as_of', '')))} · {html.escape(footnote)}"
    data-i18n-zh="{html.escape(forecaster_zh)} · 截至 {html.escape(str(forecast.get('as_of', '')))} · {html.escape(footnote_zh)}">{html.escape(forecaster)} &middot;
    as of {html.escape(str(forecast.get('as_of', '')))} &middot; {footnote}</p>
    </section>"""


def _ask_section() -> str:
    return """<section class="ask-section" id="ask"
    aria-labelledby="ask-title">
    <div class="section-heading"><div><p class="eyebrow" data-i18n="ask.eyebrow">QUESTIONS ABOUT THIS COMPANY</p>
    <h2 id="ask-title" data-i18n="ask.title">Ask about this company</h2></div>
    <span class="ask-validation" data-i18n="ask.validated">Citations and answer format checked</span></div>
    <p class="section-intro" data-i18n="ask.intro">Start with a guided research task, review the drafted
    question, then choose whether to send it. The model can use only this page's frozen evidence.</p>
    <div class="ask-layout">
      <form class="ask-form" id="ask-form">
        <details class="ask-advanced">
        <summary data-i18n="ask.advanced">Model, language &amp; sources</summary>
        <div class="ask-controls">
          <label><span data-i18n="ask.model">Model</span><select id="ask-model" name="provider" disabled>
          <option data-i18n="ask.loading_models">Loading live models…</option></select></label>
          <label><span data-i18n="ask.answer_language">Answer language</span><select id="ask-language" name="language">
          <option value="English">English</option><option value="Chinese">中文</option>
          </select></label>
          <label><span data-i18n="ask.evidence_scope">Evidence scope</span><select id="ask-scope" name="scope" disabled>
          <option data-i18n="ask.loading_scopes">Loading scopes…</option></select></label>
        </div>
        <p class="ask-scope-note" id="ask-scope-note" data-i18n="ask.scope_note_core">SEC filings and long-term fundamentals only.</p>
        </details>
        <div class="ask-step-heading"><span>1</span><div>
        <strong data-i18n="ask.choose_task">Choose what to investigate</strong>
        <small data-i18n="ask.choose_task_copy">Selecting a tab drafts a bounded question. Nothing is sent automatically.</small>
        </div></div>
        <div class="ask-task-tabs" role="tablist" aria-label="Guided research questions">
          <button type="button" role="tab" data-ask-task="filing"
          data-i18n="ask.task_filing">Latest filing</button>
          <button type="button" role="tab" data-ask-task="history"
          data-i18n="ask.task_history">History vs benchmark</button>
          <button type="button" role="tab" data-ask-task="risk"
          data-i18n="ask.task_risk">Risk experienced</button>
        </div>
        <details class="ask-more-tasks">
        <summary data-i18n="ask.more_tasks">More research questions</summary>
        <div class="ask-task-tabs" role="tablist" aria-label="More research questions">
          <button type="button" role="tab" data-ask-task="limits"
          data-i18n="ask.task_limits">Evidence limits</button>
          <button type="button" role="tab" data-ask-task="quality"
          data-i18n="ask.task_quality">Business quality</button>
          <button type="button" role="tab" data-ask-task="cash"
          data-i18n="ask.task_cash">Earnings & cash</button>
          <button type="button" role="tab" data-ask-task="capital"
          data-i18n="ask.task_capital">Per-share capital</button>
          <button type="button" role="tab" data-ask-task="thesis"
          data-i18n="ask.task_thesis">Thesis risks</button>
          <button type="button" role="tab" data-ask-task="missing"
          data-i18n="ask.task_missing">Missing evidence</button>
        </div>
        </details>
        <div class="ask-task-preview" id="ask-task-preview">
          <span data-i18n="ask.guided_prompt">GUIDED PROMPT</span>
          <strong id="ask-task-title"></strong>
          <p id="ask-task-description"></p>
        </div>
        <div class="ask-step-heading ask-review-step"><span>2</span><div>
        <strong data-i18n="ask.review_question">Review or edit the drafted question</strong>
        <small data-i18n="ask.review_question_copy">You stay in control before the request is sent.</small>
        </div></div>
        <label class="ask-question"><span data-i18n="ask.question">Question</span>
        <textarea id="ask-question" maxlength="280" rows="3"
        placeholder="What does the latest 8-K tell me?"
        data-i18n-placeholder="ask.placeholder" required></textarea></label>
        <div class="ask-submit-row"><button id="ask-submit" type="submit" disabled
        data-i18n="ask.submit">Get a cited answer</button>
        <button id="ask-stop" type="button" hidden data-i18n="ask.stop">Stop</button>
        <button id="ask-retry" type="button" hidden data-i18n="ask.retry">Retry model check</button>
        <span id="ask-status" aria-live="polite"
        data-status-key="ask.checking_models">Checking available models…</span></div>
      </form>
      <div class="ask-result" id="ask-result" aria-live="polite">
        <p class="ask-result-kicker" data-i18n="ask.scope_title">WHAT THIS DEMO CAN ANSWER</p>
        <div class="ask-scope-groups">
          <section class="ask-scope-group in-scope"><strong data-i18n="ask.in_scope">In scope</strong>
          <ul><li data-i18n="ask.in_scope_1">What the latest 8-K says, with cited passages</li>
          <li data-i18n="ask.in_scope_2">Historical return and risk versus the snapshot's fixed benchmark</li>
          <li data-i18n="ask.in_scope_3">Observed filing reaction and prior wording changes</li>
          <li data-i18n="ask.in_scope_4">Which evidence is present or missing</li></ul></section>
          <section class="ask-scope-group out-scope"><strong data-i18n="ask.out_scope">Always withheld</strong>
          <ul><li data-i18n="ask.out_scope_1">Buy, sell, or hold recommendations</li>
          <li data-i18n="ask.out_scope_2">Price targets and future forecasts</li>
          <li data-i18n="ask.out_scope_3">Uncited facts or invented numbers</li>
          <li data-i18n="ask.out_scope_4">Claims beyond the frozen evidence packet</li></ul></section>
        </div>
        <div class="ask-control-flow"><span data-i18n="ask.control_flow">
        Draft question → bounded evidence → model → validator → cited answer</span></div>
      </div>
    </div>
    <p class="ask-boundary" data-i18n="ask.boundary"><strong>Scope:</strong> explanation, not recommendation ·
    maximum 280 characters · public-demo rate limit · API keys remain server-side</p>
    </section>"""


def _evidence_context(
    scope: EvidenceScopeSummary | None,
    headlines: list[HeadlineBrief],
) -> str:
    company_headlines = [
        headline for headline in headlines if headline.source_type == "company_news"
    ][:3]
    if scope is None or not company_headlines:
        return ""

    cards = "".join(_headline_card(headline) for headline in company_headlines)
    status_label = {
        "available": "Available",
        "empty": "Empty",
        "stale": "Stale cache",
        "not_configured": "Not configured",
    }[scope.status]
    freshness = _pretty_context_time(scope.generated_at) if scope.generated_at else "Unknown"
    return f"""<section class="context-section" id="context"
    aria-labelledby="context-title">
    <div class="section-heading"><div><p class="eyebrow" data-i18n="context.eyebrow">COMPANY-SPECIFIC CONTEXT</p>
    <h2 id="context-title" data-i18n="context.title">Recent company coverage</h2></div>
    <span class="context-status {html.escape(scope.status)}"
    data-i18n="context.status_{html.escape(scope.status)}">{html.escape(status_label)}</span></div>
    <p class="section-intro" data-i18n="context.intro">Only headlines matched to this ticker appear here. They add
    context but are not used to calculate returns or filing reactions.</p>
    <p class="context-freshness"><span data-i18n="context.refreshed">Refreshed</span> {html.escape(freshness)}</p>
    <div class="headline-list">{cards}</div>
    </section>"""


def _headline_card(headline: HeadlineBrief) -> str:
    return (
        f'<article class="headline-card" data-citation="{html.escape(headline.citation)}">'
        f'<div class="headline-meta"><span>{html.escape(headline.publisher)}</span>'
        f"<span>{html.escape(_pretty_context_time(headline.published_at))}</span></div>"
        f"<h3>{html.escape(headline.headline)}</h3>"
        f'<a href="{html.escape(headline.url)}" target="_blank" '
        'rel="noopener noreferrer" data-i18n="context.read_source">Read source ↗</a></article>'
    )


def _pretty_context_time(value: str) -> str:
    return datetime.fromisoformat(value).strftime("%b %d, %Y · %H:%M %Z").rstrip(" ·")


def _profile_meta(profile: dict[str, Any]) -> str:
    coverage = profile.get("coverage") or {}
    price_start = html.escape(str(coverage.get("price_start", "Unavailable")))
    price_end = html.escape(str(coverage.get("price_end", "Unavailable")))
    filing_count = html.escape(str(coverage.get("filings_in_snapshot", 0)))
    source_url = profile.get("source_url")
    source_label = profile.get("source_label")
    source = ""
    if source_url and source_label:
        source = (
            f'<a href="{html.escape(str(source_url))}" target="_blank" rel="noreferrer">'
            f'<span data-i18n-en="{html.escape(str(source_label))} ↗" data-i18n-zh="SEC EDGAR 公司记录 ↗">{html.escape(str(source_label))} ↗</span></a>'
        )
    cik = profile.get("cik")
    cik_label = f"CIK {html.escape(str(cik))}" if cik else "CIK unavailable"
    return (
        '<div class="profile-meta">'
        f"<span>{cik_label}</span>{source}"
        f'<span><span data-i18n="profile.prices">Prices</span> {price_start}—{price_end}</span>'
        f'<span data-i18n="profile.filings" data-i18n-count="{filing_count}">{filing_count} recent filings in snapshot</span>'
        "</div>"
    )


def _brief(snapshot: CompanySnapshot) -> str:
    latest = snapshot.latest_filings[0] if snapshot.latest_filings else None
    changed = _first_claim(snapshot.explanation, "what_changed")
    uncertainty = _first_claim(snapshot.explanation, "uncertainties")
    changed_links = "".join(
        _citation_link(value) for value in changed.get("citations", [])
    )
    if latest:
        filing_title = latest.items[0]["label"] if latest.items else "Corporate update"
        filing_title_zh = (
            latest.items[0].get("label_zh") or filing_title
            if latest.items
            else "公司更新"
        )
        filing_title_attrs = (
            f' data-i18n="item.{html.escape(latest.items[0]["code"]) if latest.items else "unknown"}" data-i18n-en="{html.escape(filing_title)}" '
            f'data-i18n-zh="{html.escape(str(filing_title_zh))}"'
        )
        filing_meta = (
            f'<span>{html.escape(latest.form)}</span>'
            f'<span data-local-date="{html.escape(latest.accepted_at)}">{html.escape(_pretty_date(latest.accepted_at))}</span>'
        )
        if latest.reaction:
            filing_meta += (
                f'<span>{_signed_percent(latest.reaction.benchmark_adjusted_move)} '
                f'<span data-i18n="reaction.versus">vs</span> {html.escape(snapshot.benchmark)}</span>'
            )
        source_link = (
            f'<a href="{html.escape(latest.source_url)}" target="_blank" '
            'rel="noreferrer" data-i18n="filing.open_sec">Open SEC filing ↗</a>'
        )
    else:
        filing_title_attrs = ' data-i18n="filing.no_local_filing"'
        filing_title = "No local filing"
        filing_meta = '<span data-i18n="filing.evidence_unavailable">Evidence unavailable</span>'
        source_link = ""
    changed_en = str(changed.get("text", "Not available."))
    changed_zh = str(changed.get("text_zh") or changed_en)
    uncertainty_en = str(uncertainty.get("text", "Not available."))
    uncertainty_zh = str(uncertainty.get("text_zh") or uncertainty_en)
    return f"""
    <article class="brief-card brief-lead observed">
      <div class="brief-card-heading"><span data-i18n="brief.latest_disclosure">Latest SEC disclosure</span>{source_link}</div>
      <h3{filing_title_attrs}>{html.escape(filing_title)}</h3>
      <p data-i18n="brief.changed_claim" data-i18n-en="{html.escape(changed_en)}"
      data-i18n-zh="{html.escape(changed_zh)}">{html.escape(changed_en)}</p>
      <div class="brief-meta">{filing_meta}</div><div class="claim-links">{changed_links}</div>
      <a href="#filings" data-i18n="brief.explore_filings">Read the filing evidence ↓</a>
    </article>
    <article class="brief-card brief-numbers calculated">
      <span data-i18n="brief.selected_period">Selected historical period</span>
      <div class="brief-metrics">
        <div><strong id="total-return"></strong><small data-i18n="brief.total_return">Total return</small></div>
        <div><strong id="max-drawdown"></strong><small data-i18n="brief.max_drawdown">Maximum drawdown</small></div>
      </div>
      <p><span id="brief-period-label"></span> <span data-i18n="brief.period_context">of adjusted daily prices versus
      {html.escape(snapshot.benchmark)}. Context, not a forecast.</span></p>
      <a href="#performance"
      data-i18n="brief.explore_history">Explore the full history ↓</a>
    </article>
    <article class="brief-card brief-limit guardrail">
      <span data-i18n="brief.boundary">Boundary:</span>
      <p data-i18n="brief.uncertainty_claim" data-i18n-en="{html.escape(uncertainty_en)}"
      data-i18n-zh="{html.escape(uncertainty_zh)}">{html.escape(uncertainty_en)}</p>
    </article>"""


def _first_claim(explanation: dict, section: str) -> dict:
    claims = explanation.get(section, [])
    return claims[0] if claims else {"text": "Not available.", "citations": []}


def _mode_label(mode: Any) -> str:
    if mode == "grounded_llm":
        return "Source-bounded AI"
    if mode == "deterministic_fallback":
        return "Source-backed summary"
    return html.escape(str(mode or "Explanation unavailable"))


def _filing_card(filing: FilingBrief, index: int, benchmark: str) -> str:
    item_chips = "".join(
        f'<span class="item-chip" title="{html.escape(item["label"])}">'
        f'{html.escape(item["code"])} · '
        f'<span data-i18n="item.{html.escape(item["code"])}" '
        f'data-i18n-en="{html.escape(item["label"])}" '
        f'data-i18n-zh="{html.escape(item.get("label_zh") or item["label"])}">'
        f'{html.escape(item["label"])}</span></span>'
        for item in filing.items
    )
    reaction = (
        '<span data-i18n="filing.reaction_not_measurable">Reaction not yet measurable</span>'
        if filing.reaction is None
        else f'{_signed_percent(filing.reaction.benchmark_adjusted_move)} <span data-i18n="reaction.versus">vs</span> {html.escape(benchmark)}'
    )
    entities = "".join(_entity_chip(entity) for entity in filing.entities)
    if not entities:
        entities = "".join(
            f'<a class="number-chip" href="#{_dom_id(number["citation"])}">'
            f'{html.escape(number["value"])}</a>' for number in filing.key_numbers
        )
    entities = entities or (
        '<span class="missing" data-i18n="filing.no_entities">'
        "No cited entity in the primary document</span>"
    )
    passages = "".join(_passage(passage, filing.entities) for passage in filing.passages)
    if not passages:
        passages = (
            '<p class="missing" data-i18n="filing.no_passages">'
            "No passage passed the deterministic relevance threshold.</p>"
        )
    body = f"""<div class="filing-items">{item_chips}</div>
      {_reaction_block(filing, benchmark)}
      {_comparison_block(filing)}
      <details class="source-details"><summary data-i18n="filing.source_facts">Source passages and extracted facts</summary>
      <div class="filing-columns"><div><h3 data-i18n="filing.extracted_facts">Extracted facts</h3><div class="number-list">{entities}</div>
      <h3 data-i18n="filing.relevant_passages">Relevant passages</h3><div class="passages">{passages}</div></div>
      <aside><span data-i18n="filing.source_record">Source record</span><code>{html.escape(filing.accession)}</code>
      <a href="{html.escape(filing.source_url)}" target="_blank" rel="noreferrer" data-i18n="filing.open_sec">Open SEC filing ↗</a>
      <p data-i18n="filing.source_note">SEC excerpts remain in the filed language so citations can be verified exactly.</p></aside></div></details>"""
    title_text = filing.items[0]["label"] if filing.items else "Corporate update"
    title_zh = filing.items[0].get("label_zh") or title_text if filing.items else "公司更新"
    title = html.escape(title_text)
    localized_title = (
        f'<span data-i18n="item.{html.escape(filing.items[0]["code"])}" '
        f'data-i18n-en="{title}" data-i18n-zh="{html.escape(title_zh)}">{title}</span>'
        if filing.items
        else f'<span data-i18n-en="{title}" data-i18n-zh="{html.escape(title_zh)}">{title}</span>'
    )
    accepted = html.escape(_pretty_date(filing.accepted_at))
    if index == 0:
        return f"""<article class="filing-card filing-lead">
      <header class="filing-lead-header"><span class="filing-form">{html.escape(filing.form)}</span>
      <div><p class="eyebrow" data-i18n="filing.latest">Latest disclosure</p>
      <h3>{localized_title}</h3>
      <small><span data-i18n="filing.accepted">Accepted</span> <span data-local-date="{html.escape(filing.accepted_at)}">{accepted}</span></small></div>
      <a href="{html.escape(filing.source_url)}" target="_blank" rel="noreferrer"
      data-i18n="filing.open_sec">Open SEC filing ↗</a></header>
      <div class="filing-body">{body}</div></article>"""
    return f"""<details class="filing-card">
      <summary><div><span class="filing-form">{html.escape(filing.form)}</span>
      <strong>{localized_title}</strong>
      <small><span data-i18n="filing.accepted">Accepted</span> <span data-local-date="{html.escape(filing.accepted_at)}">{accepted}</span></small></div>
      <div class="filing-summary-meta"><span>{reaction}</span>
      <span data-i18n="filing.view_evidence">View evidence</span><i>⌄</i></div></summary>
      <div class="filing-body">{body}</div>
      </details>"""


def _filing_timeline(points: list[FilingTimelinePoint], benchmark: str) -> str:
    if not points:
        return ""
    events = []
    for point in points:
        if point.reaction is None:
            direction = "unavailable"
            move = (
                '<span data-i18n="reaction.unavailable_move">Reaction unavailable</span>'
            )
            context = (
                '<span data-i18n="reaction.missing_session_bars">'
                "Required session bars are not both cached</span>"
            )
        else:
            value = point.reaction.benchmark_adjusted_move
            direction = "positive" if value > 0 else "negative" if value < 0 else "flat"
            move = f"{_signed_percent(value)} vs {benchmark}"
            context = (
                f"{point.reaction.magnitude_percentile:.0%} of earlier filings were smaller"
                if point.reaction.magnitude_percentile is not None
                else f"{point.reaction.prior_sample_size} earlier measurable filings"
            )
        accepted = datetime.fromisoformat(point.accepted_at).strftime("%b %d, %Y")
        label_zh = point.item_label_zh or point.item_label
        events.append(
            f'<a class="timeline-event {direction}" href="{html.escape(point.source_url)}" '
            f'target="_blank" rel="noreferrer"><span>{html.escape(accepted)}</span>'
            f'<i aria-hidden="true"></i><strong data-i18n="item.{html.escape(point.item_code)}" '
            f'data-i18n-en="{html.escape(point.item_label)}" '
            f'data-i18n-zh="{html.escape(label_zh)}">{html.escape(point.item_label)}</strong>'
            f'<small>Item {html.escape(point.item_code)}</small><b>{move}</b>'
            f'<em>{context}</em></a>'
        )
    return f"""<section class="timeline-panel" aria-label="Recent filing timeline">
    <div class="timeline-heading"><div><span data-i18n="timeline.title">Recent filing timeline</span>
    <strong data-i18n="timeline.subtitle">What arrived, and how the next eligible session moved</strong></div>
    <small data-i18n="timeline.range" data-i18n-count="{len(points)}">Oldest → newest · latest {len(points)}</small></div>
    <div class="timeline-track">{''.join(events)}</div>
    <p data-i18n="timeline.boundary">Relative moves are open-to-close company returns less {html.escape(benchmark)};
    they are historical context, not event forecasts.</p></section>"""


def _reaction_block(filing: FilingBrief, benchmark: str) -> str:
    reaction = filing.reaction
    if reaction is None:
        return (
            '<div class="reaction-empty"><strong data-i18n="reaction.unavailable">'
            'Market reaction not yet measurable</strong><span data-i18n="reaction.missing_bars">'
            "The required company and benchmark bars are not both present for the "
            "first eligible session.</span></div>"
        )
    if reaction.magnitude_percentile is None:
        history_value = (
            '<span data-i18n="reaction.building_history">Building history</span>'
        )
        suffix = "s" if reaction.prior_sample_size != 1 else ""
        history_note = (
            f'<span data-i18n="reaction.history_note_building" '
            f'data-i18n-count="{reaction.prior_sample_size}" data-i18n-suffix="{suffix}">'
            f"{reaction.prior_sample_size} earlier measurable filing"
            f"{suffix}; shown after 5</span>"
        )
    else:
        pct = f"{reaction.magnitude_percentile:.0%}"
        history_value = (
            f'<span data-i18n="reaction.more_extreme" data-i18n-pct="{html.escape(pct)}">'
            f"More extreme than {pct}</span>"
        )
        history_note = (
            f'<span data-i18n="reaction.history_note_extreme" '
            f'data-i18n-count="{reaction.prior_sample_size}">'
            f"of {reaction.prior_sample_size} earlier measurable filings</span>"
        )
    asset_move = _signed_percent(reaction.asset_open_to_close)
    benchmark_move = _signed_percent(reaction.benchmark_open_to_close)
    relative_move = _signed_percent(reaction.benchmark_adjusted_move)
    session = datetime.fromisoformat(reaction.session).strftime("%b %d, %Y")
    return f"""<section class="reaction-panel" aria-label="Observed filing market reaction">
    <div class="reaction-heading"><div><span data-i18n="reaction.title">What happened next</span>
    <strong><span data-local-date="{html.escape(reaction.session)}">{html.escape(session)}</span> · <span data-i18n="reaction.first_session">first eligible session</span></strong></div>
    <small data-i18n="reaction.observed">Observed, not attributed</small></div>
    <div class="reaction-grid">
    <div><span data-i18n="reaction.company_move">Company move</span><strong>{html.escape(asset_move)}</strong>
    <small data-i18n="reaction.open_close">open to close</small></div>
    <div><span data-i18n="reaction.after_benchmark">After subtracting {html.escape(benchmark)}</span><strong>{html.escape(relative_move)}</strong>
    <small>{html.escape(asset_move)} <span data-i18n="reaction.less">less</span> {html.escape(benchmark_move)}</small></div>
    <div><span data-i18n="reaction.compared">Compared with past filings</span><strong>{history_value}</strong>
    <small>{history_note}</small></div></div>
    <p data-i18n="reaction.boundary">This is the first session whose opening followed SEC acceptance. It shows what
    happened next; it does not claim the filing caused the move.</p></section>"""


def _comparison_block(filing: FilingBrief) -> str:
    comparison = filing.comparison
    if comparison is None:
        return (
            '<div class="comparison-empty"><strong data-i18n="comparison.unavailable">'
            'Prior comparison unavailable</strong><span data-i18n="comparison.no_prior">'
            "No earlier filing with the same form and primary event type exists in "
            "the local issuer history.</span></div>"
        )
    counts = comparison.counts
    substantive_count = sum(counts.get(kind, 0) for kind in ("changed", "added", "removed"))
    count_chips = "" if not substantive_count else "".join(
        f'<span class="change-count {kind}">{counts.get(kind, 0)} {kind}</span>'
        for kind in ("changed", "added", "removed")
        if counts.get(kind, 0)
    )
    selected = _representative_changes(comparison.changes)
    if selected:
        changes = "".join(_change_card(change) for change in selected)
    else:
        changes = (
            '<div class="comparison-clear"><strong data-i18n="comparison.no_change">'
            'No substantive wording change detected</strong>'
            '<span data-i18n="comparison.no_change_note">'
            "Date and fiscal-quarter roll-forwards are treated as routine updates. "
            "Referenced exhibits may still contain detail outside the cached primary document.</span>"
            "</div>"
        )
    return f"""<section class="comparison-panel" aria-label="Prior comparable filing changes">
    <div class="comparison-heading"><div><span data-i18n="comparison.title">What changed vs the last similar filing</span>
    <strong data-local-date="{html.escape(comparison.prior_accepted_at)}">{html.escape(_pretty_date(comparison.prior_accepted_at))}</strong></div>
    <a href="{html.escape(comparison.prior_source_url)}" target="_blank" rel="noreferrer">
    <span data-i18n="comparison.prior">Prior filing ↗</span></a></div><div class="change-counts">{count_chips}</div>
    <div class="change-list">{changes}</div></section>"""


def _representative_changes(
    changes: list[FilingChange], limit: int = 4
) -> list[FilingChange]:
    selected = []
    for kind in ("changed", "added", "removed"):
        match = next((change for change in changes if change.kind == kind), None)
        if match is not None:
            selected.append(match)
    selected.extend(change for change in changes if change not in selected)
    return selected[:limit]


def _change_card(change: FilingChange) -> str:
    current = _change_quote("Current", change.current) if change.current else ""
    prior = _change_quote("Prior", change.prior) if change.prior else ""
    similarity = (
        f'<span class="similarity">{change.similarity:.0%} text match</span>'
        if change.similarity is not None
        else ""
    )
    return (
        f'<article class="change-card {html.escape(change.kind)}">'
        f'<header><strong>{html.escape(change.kind.title())}</strong>{similarity}</header>'
        f"{current}{prior}</article>"
    )


def _change_quote(label: str, citation: Citation) -> str:
    return (
        f'<div class="change-quote"><span>{html.escape(label)}</span>'
        f'<p>{html.escape(citation.text)}</p>'
        f'<a href="{html.escape(citation.source_url)}" target="_blank" rel="noreferrer">'
        f'{html.escape(citation.anchor)} ↗</a></div>'
    )


def _entity_chip(entity: FilingEntity) -> str:
    label = entity.kind.replace("_", " ")
    title = f"{label}; normalized {entity.normalized_value} {entity.unit}"
    return (
        f'<a class="number-chip entity-chip" href="#{_dom_id(entity.citation)}" '
        f'title="{html.escape(title)}"><small>{html.escape(label)}</small>'
        f'{html.escape(entity.text)}</a>'
    )


def _passage(citation: Citation, entities: list[FilingEntity] | None = None) -> str:
    cited = sorted(
        (entity for entity in entities or [] if entity.citation == citation.anchor),
        key=lambda entity: entity.source_start,
    )
    text = _highlight_entities(citation.text, cited)
    return (
        f'<blockquote id="{_dom_id(citation.anchor)}"><p>{text}</p>'
        f'<a href="{html.escape(citation.source_url)}" target="_blank" rel="noreferrer">'
        f'{html.escape(citation.anchor)} ↗</a></blockquote>'
    )


def _highlight_entities(text: str, entities: list[FilingEntity]) -> str:
    rendered = []
    position = 0
    for entity in entities:
        if (
            entity.source_start < position
            or text[entity.source_start:entity.source_end] != entity.text
        ):
            continue
        rendered.append(html.escape(text[position:entity.source_start]))
        rendered.append(
            f'<mark class="entity-mark {html.escape(entity.kind)}" '
            f'title="{html.escape(entity.kind.replace("_", " "))}">'
            f'{html.escape(entity.text)}</mark>'
        )
        position = entity.source_end
    rendered.append(html.escape(text[position:]))
    return "".join(rendered)


def _citation_link(value: str) -> str:
    if value.startswith("metric:"):
        return (
            '<a href="#performance" class="metric-citation" '
            'data-i18n="citation.metric">Calculated metric</a>'
        )
    return (
        f'<a href="#{_dom_id(value)}" class="source-citation" '
        'data-i18n="citation.source">Source passage</a>'
    )


def _metric(label: str, element_id: str, definition: str, translation_key: str) -> str:
    return (
        f'<article class="metric-card"><span><span data-i18n="{translation_key}">'
        f'{html.escape(label)}</span><i title="{html.escape(definition)}" '
        f'data-i18n-title="{translation_key}.definition">?</i></span>'
        f'<strong id="{element_id}"></strong><small data-i18n="{translation_key}.definition">'
        f'{html.escape(definition)}</small></article>'
    )


BENCHMARK_DEFINITIONS = {
    "SPY": "SPY tracks the S&P 500: use it to compare this stock with large US companies "
    "over the same period.",
    "QQQ": "QQQ tracks the Nasdaq-100: the 100 largest non-financial companies listed on "
    "Nasdaq. It leans toward technology but is not a pure technology index.",
}


def _benchmark_definition(symbol: str) -> str:
    return BENCHMARK_DEFINITIONS.get(symbol, f"{symbol} is the comparison benchmark.")


def _benchmark_buttons(snapshot: CompanySnapshot) -> str:
    """One benchmark at a time; a pair without usable matched history is disabled."""
    if not snapshot.benchmark_comparisons:
        return ""
    default = html.escape(snapshot.benchmark)
    buttons = [(
        f'<button class="benchmark-button active" data-benchmark="{default}" '
        f'type="button" aria-pressed="true">{default}</button>'
    )]
    for symbol, comparison in snapshot.benchmark_comparisons.items():
        disabled = comparison.get("status") != "available"
        reason = comparison.get("reason") or ""
        buttons.append(
            f'<button class="benchmark-button" data-benchmark="{html.escape(symbol)}" '
            f'data-unavailable-reason="{html.escape(reason)}" type="button" '
            f'aria-pressed="false"{" disabled" if disabled else ""}>{html.escape(symbol)}</button>'
        )
    return (
        '<div class="benchmark-control" role="group" aria-label="Comparison benchmark">'
        f'{"".join(buttons)}</div>'
    )


def _default_period(snapshot: CompanySnapshot) -> str:
    years = round((datetime.fromisoformat(snapshot.period["end"]) -
                   datetime.fromisoformat(snapshot.period["start"])).days / 365.25)
    candidate = f"{years}Y"
    return candidate if candidate in snapshot.period_options else next(iter(snapshot.period_options))


def _pretty_date(value: str) -> str:
    return datetime.fromisoformat(value).strftime("%b %d, %Y · %H:%M ET")


def _dom_id(value: str) -> str:
    return "citation-" + re.sub(r"[^a-zA-Z0-9_-]+", "-", value)


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _signed_percent(value: float) -> str:
    return f"{value:+.1%}" if value else "0.0%"


def _script(default_period: str, ticker: str, benchmark: str) -> str:
    translations = json.dumps(
        {
            "en": {
                "profile.prices": "Prices",
                "profile.filings": "{count} recent filings in snapshot",

                "reaction.first_session": "first eligible session",
                "reaction.less": "less",
                "reaction.versus": "vs",
                "footer.universe": "Universe: a convenience sample of current large caps, not a point-in-time index",
                "footer.snapshot": "Snapshot",
                "footer.market": "Market through",
                "footer.sources": "SEC + adjusted daily prices",
                "ask.original_language": "Answer text stays in its original language. Ask again to generate an answer in the selected language.",

                "nav.earnings": "Financial results",
                "nav.what": "What this is",
                "nav.research": "How this is audited",
                "nav.find": "Find a company",
                "nav.overview": "Overview",
                "nav.ask": "Ask AI",
                "nav.history": "History",
                "nav.filings": "Filings",
                "nav.company_news": "Company news",
                "nav.trust": "Evidence, not prediction",
                "workspace.eyebrow": "ON THIS PAGE",
                "workspace.title": "Read the brief, then verify below.",
                "hero.eyebrow": "COMPANY OVERVIEW · SOURCE-BACKED",
                "hero.latest_close": "Latest adjusted close",
                "hero.observed": "Observed",
                "brief.eyebrow": "ONE-MINUTE BRIEF",
                "brief.title": "What matters on this page",
                "brief.intro": ("Start with the latest disclosure, then the historical "
                               "picture. Every number links to its source."),
                "brief.latest_disclosure": "Latest SEC disclosure",
                "brief.selected_period": "Selected historical period",
                "brief.total_return": "Total return",
                "brief.max_drawdown": "Maximum drawdown",
                "brief.period_context": (
                    "of adjusted daily prices versus {benchmark}. Context, not a forecast."
                ),
                "brief.explore_history": "Explore the full history ↓",
                "brief.explore_filings": "Read the filing evidence ↓",
                "brief.boundary": "Boundary:",
                "brief.metric_revenue": "Revenue",
                "brief.metric_gross_margin": "Gross margin",
                "brief.metric_operating_margin": "Operating margin",
                "brief.metric_free_cash_flow": "Free cash flow",
                "brief.metric_fcf_per_share": "Free cash flow / share",
                "brief.metric_diluted_shares": "Diluted shares",
                "brief.metric_share_change": "Diluted share change",
                "brief.trend_up": "Up",
                "brief.trend_down": "Down",
                "brief.trend_flat": "Flat",
                "brief.coverage_complete": "complete",
                "brief.coverage_partial": "partial",
                "brief.coverage_missing": "missing",
                "reaction.building_history": "Building history",
                "reaction.more_extreme": "More extreme than {pct}",
                "reaction.history_note_building": (
                    "{count} earlier measurable filing{suffix}; shown after 5"
                ),
                "reaction.history_note_extreme": "of {count} earlier measurable filings",
                "reaction.unavailable_move": "Reaction unavailable",
                "reaction.missing_session_bars": "Required session bars are not both cached",
                "timeline.title": "Recent filing timeline",
                "timeline.subtitle": "What arrived, and how the next eligible session moved",
                "timeline.range": "Oldest → newest · latest {count}",
                "timeline.boundary": (
                    "Relative moves are open-to-close company returns less {benchmark}; "
                    "they are historical context, not event forecasts."
                ),
                "filing.reaction_not_measurable": "Reaction not yet measurable",
                "item.1.01": "Material agreement entered",
                "item.1.02": "Material agreement terminated",
                "item.1.03": "Bankruptcy or receivership",
                "item.2.01": "Asset acquisition or disposition",
                "item.2.02": "Results of operations (earnings)",
                "item.2.03": "Direct financial obligation created",
                "item.2.04": "Triggering event accelerating an obligation",
                "item.2.05": "Costs from exit or disposal",
                "item.2.06": "Material impairment",
                "item.3.01": "Delisting or listing-rule failure",
                "item.3.02": "Unregistered equity sale",
                "item.3.03": "Material modification to security holder rights",
                "item.4.01": "Auditor changed",
                "item.4.02": "Prior financial statements not reliable",
                "item.5.01": "Change in control",
                "item.5.02": "Director or principal officer change",
                "item.5.03": "Fiscal year or bylaw amendment",
                "item.5.07": "Shareholder vote results",
                "item.7.01": "Regulation FD disclosure",
                "item.8.01": "Other events",
                "item.9.01": "Financial statements and exhibits",
                "item.other": "Other disclosure",
                "explain.no_filing": "No filing is available for this company in the local dataset.",
                "ask.task_quality": "Business quality",
                "ask.task_cash": "Earnings & cash",
                "ask.task_capital": "Per-share capital",
                "ask.task_thesis": "Thesis risks",
                "ask.task_missing": "Missing evidence",
                "ask.task_quality_title": "Review multi-year business quality",
                "ask.task_quality_copy": (
                    "Uses source-linked annual revenue, margins, free cash flow per share, "
                    "and diluted shares."
                ),
                "ask.task_quality_question": (
                    "Using only the annual fundamentals evidence, how did revenue, gross "
                    "margin, operating margin, free cash flow per share, and diluted shares "
                    "change over the available fiscal years?"
                ),
                "ask.task_cash_title": "Compare earnings and cash quality",
                "ask.task_cash_copy": (
                    "Uses net income, operating cash flow, free cash flow, and conversion ratios."
                ),
                "ask.task_cash_question": (
                    "What do operating cash flow, free cash flow, and cash conversion say "
                    "about earnings quality in the latest comparable fiscal years?"
                ),
                "ask.task_capital_title": "Inspect per-share capital allocation",
                "ask.task_capital_copy": (
                    "Uses diluted shares, free cash flow per share, buybacks, and dividends "
                    "when present."
                ),
                "ask.task_capital_question": (
                    "How did diluted shares and free cash flow per share change, and what "
                    "capital-return evidence is present?"
                ),
                "ask.task_thesis_title": "Surface thesis risks in the evidence",
                "ask.task_thesis_copy": (
                    "Uses filing passages, reaction context, and fundamentals coverage warnings."
                ),
                "ask.task_thesis_question": (
                    "Which cited filings, reactions, or fundamentals gaps most clearly "
                    "challenge a durable long-term business thesis?"
                ),
                "ask.task_missing_title": "List missing evidence",
                "ask.task_missing_copy": (
                    "Uses interpretation limits and fundamentals coverage status."
                ),
                "ask.task_missing_question": (
                    "What important evidence is missing from this page for judging business "
                    "quality, cash quality, or per-share value creation?"
                ),
                "mode.grounded": "Source-bounded AI",
                "mode.fallback": "Source-backed summary",
                "mode.unavailable": "Explanation unavailable",
                "signal.eyebrow": "THIS FILING VS ITS OWN HISTORY",
                "signal.title": "Is this unusual for this company?",
                "signal.intro": ("Every number here compares this filing with earlier "
                    "filings from the same issuer. Nothing compares it with other "
                    "companies, and nothing here is a view on price direction."),
                "signal.why": "Why",
                "signal.boundary": ("This estimates how large a reaction may be, not "
                    "which way it goes. It is a reading priority, not investment advice."),
                "signal.probability": "chance of an unusually large reaction",
                "signal.base": "how often this issuer clears its own bar",
                "signal.history": "earlier filings behind the comparison",
                "signal.chart_x": "Unusual language \u2192",
                "signal.chart_y": "\u2191 Reaction size",
                "signal.state.read_now": "Read now",
                "signal.state.monitor": "Monitor",
                "signal.state.routine": "Routine",
                "signal.state.insufficient_history": "Not enough history",
                "signal.state.withheld": "Withheld",
                "nav.signal": "This filing",
                "nav.volatility": "Expected range",
                "vol.eyebrow": "THE NEXT {count} SESSIONS",
                "vol.title": "How wide a range to expect",
                "vol.intro": ("How much this stock is expected to move over the next "
                    "month, as a range rather than a number. It says nothing about "
                    "which way \u2014 a wide range is as consistent with good news as "
                    "with bad."),
                "vol.median": "most likely, annualised",
                "vol.band": "80% of the time, in this range",
                "vol.usual": "this issuer\u2019s usual level",
                "vol.state.typical_for_this_issuer": "Typical for this issuer",
                "vol.state.slightly_elevated": "Slightly elevated",
                "vol.state.elevated": "Elevated",
                "vol.state.unusually_calm": "Unusually calm",
                "ask.eyebrow": "QUESTIONS ABOUT THIS COMPANY",
                "ask.title": "Ask about this company",
                "ask.validated": "Citations and answer format checked",
                "ask.intro": (
                    "Start with a guided research task, review the drafted question, then "
                    "choose whether to send it. The model can use only this page's frozen "
                    "evidence."
                ),
                "ask.advanced": "Model, language & sources",
                "ask.more_tasks": "More research questions",
                "ask.model": "Model",
                "ask.evidence_scope": "Evidence scope",
                "ask.loading_scopes": "Loading scopes…",
                "ask.scope_core": "Core financials",
                "ask.scope_company": "Company news",
                "ask.scope_market": "Market context",
                "ask.scope_all": "All evidence",
                "ask.scope_note_core": "SEC filings and long-term fundamentals only.",
                "ask.scope_note_company": "Core financials plus recent headlines about this company.",
                "ask.scope_note_market": "Core financials plus broad market and sector headlines.",
                "ask.scope_note_all": "Core financials, company news and market context together.",
                "ask.loading_models": "Loading live models…",
                "ask.answer_language": "Answer language",
                "ask.question": "Question",
                "ask.placeholder": "What does the latest 8-K tell me?",
                "ask.choose_task": "Choose what to investigate",
                "ask.choose_task_copy": (
                    "Selecting a tab drafts a bounded question. Nothing is sent automatically."
                ),
                "ask.task_filing": "Latest filing",
                "ask.task_history": "History vs benchmark",
                "ask.task_risk": "Risk experienced",
                "ask.task_limits": "Evidence limits",
                "ask.guided_prompt": "GUIDED PROMPT",
                "ask.review_question": "Review or edit the drafted question",
                "ask.review_question_copy": (
                    "You stay in control before the request is sent."
                ),
                "ask.task_filing_title": "Explain the newest disclosure",
                "ask.task_filing_copy": (
                    "Uses the latest cached 8-K, extracted facts, and source passages."
                ),
                "ask.task_filing_question": (
                    "What does the latest 8-K say, and which cited passages support "
                    "the answer?"
                ),
                "ask.task_history_title": "Compare historical performance",
                "ask.task_history_copy": (
                    "Uses calculated returns for the selected period and the same-date "
                    "{benchmark} comparison."
                ),
                "ask.task_history_question": (
                    "How did {ticker} perform versus {benchmark} over the selected "
                    "historical period?"
                ),
                "ask.task_risk_title": "Explain the risk that actually occurred",
                "ask.task_risk_copy": (
                    "Uses drawdown, volatility, worst day, beta, and recovery metrics."
                ),
                "ask.task_risk_question": (
                    "What risk did {ticker} experience in the selected period, and what "
                    "can these historical metrics not predict?"
                ),
                "ask.task_limits_title": "Audit the evidence boundary",
                "ask.task_limits_copy": (
                    "Identifies what is cached, what is missing, and what the page "
                    "cannot establish."
                ),
                "ask.task_limits_question": (
                    "What evidence is included and excluded, and what conclusions "
                    "cannot be supported?"
                ),
                "ask.submit": "Get a cited answer",
                "ask.retry": "Retry model check",
                "ask.checking_models": "Checking available models…",
                "ask.scope_title": "WHAT THIS DEMO CAN ANSWER",
                "ask.in_scope": "In scope",
                "ask.in_scope_1": "What the latest 8-K says, with cited passages",
                "ask.in_scope_2": (
                    "Historical return and risk versus {benchmark}, this snapshot's fixed "
                    "benchmark, even when History shows another comparison"
                ),
                "ask.in_scope_3": "Observed filing reaction and prior wording changes",
                "ask.in_scope_4": "Which evidence is present or missing",
                "ask.out_scope": "Always withheld",
                "ask.out_scope_1": "Buy, sell, or hold recommendations",
                "ask.out_scope_2": "Price targets and future forecasts",
                "ask.out_scope_3": "Uncited facts or invented numbers",
                "ask.out_scope_4": "Claims beyond the frozen evidence packet",
                "ask.control_flow": (
                    "Draft question → bounded evidence → model → validator → cited answer"
                ),
                "ask.boundary": (
                    "Scope: explanation, not recommendation · maximum 280 characters · "
                    "public-demo rate limit · API keys remain server-side"
                ),
                "performance.eyebrow": "HISTORICAL INVESTMENT PICTURE",
                "performance.title": "What happened to $10,000?",
                "performance.intro": (
                    "Adjusted buy-and-hold history versus {benchmark} over the exact same "
                    "dates. Historical context, not expected return."
                ),
                "performance.ending_value": "Ending value",
                "performance.more_risk": "More risk metrics",
                "metric.return": "Annualized return",
                "metric.return.definition": "Compound annual growth rate; historical, not forecast.",
                "metric.volatility": "Annualized volatility",
                "metric.volatility.definition": "Standard deviation of daily returns, annualized.",
                "metric.beta": "Beta vs {benchmark}",
                "metric.beta.definition": (
                    "Sensitivity to benchmark daily returns; 1.0 moves roughly with the benchmark."
                ),
                "metric.correlation": "Correlation vs {benchmark}",
                "metric.correlation.definition": (
                    "How closely daily returns moved together; ranges from -1 to +1."
                ),
                "metric.current_drawdown": "Current drawdown",
                "metric.current_drawdown.definition": (
                    "Distance below the highest adjusted value in the period."
                ),
                "metric.worst_day": "Worst day",
                "metric.worst_day.definition": (
                    "Largest single-session adjusted-price decline in the selected period."
                ),
                "filings.eyebrow": "FILING INTELLIGENCE",
                "filings.title": "Recent 8-K disclosures",
                "filings.latest_accepted": "Latest filing accepted",
                "filings.sec_checked": "SEC checked",
                "filings.sec_collected": "SEC cache collected",
                "filings.sec_unavailable": "SEC cache time unavailable",
                "filings.intro": (
                    "The newest filing stays open. Read what arrived, what the next eligible "
                    "session did, and whether the wording changed in a substantive way."
                ),
                "filing.accepted": "Accepted",
                "filing.latest": "Latest disclosure",
                "filing.view_evidence": "View evidence",
                "filing.source_facts": "Source passages and extracted facts",
                "filing.extracted_facts": "Extracted facts",
                "filing.relevant_passages": "Relevant passages",
                "filing.no_local_filing": "No local filing",
                "filing.evidence_unavailable": "Evidence unavailable",
                "filing.no_entities": "No cited entity in the primary document",
                "filing.no_passages": (
                    "No passage passed the deterministic relevance threshold."
                ),
                "filing.source_record": "Source record",
                "filing.open_sec": "Open SEC filing ↗",
                "filing.source_note": (
                    "SEC excerpts remain in the filed language so citations can be verified exactly."
                ),
                "reaction.title": "What happened next",
                "reaction.observed": "Observed, not attributed",
                "reaction.company_move": "Company move",
                "reaction.open_close": "open to close",
                "reaction.after_benchmark": "After subtracting {benchmark}",
                "reaction.compared": "Compared with past filings",
                "reaction.unavailable": "Market reaction not yet measurable",
                "reaction.missing_bars": (
                    "The required company and benchmark bars are not both present for "
                    "the first eligible session."
                ),
                "reaction.boundary": (
                    "This is the first session whose opening followed SEC acceptance. It shows "
                    "what happened next; it does not claim the filing caused the move."
                ),
                "comparison.title": "What changed vs the last similar filing",
                "comparison.prior": "Prior filing ↗",
                "comparison.unavailable": "Prior comparison unavailable",
                "comparison.no_prior": (
                    "No earlier filing with the same form and primary event type exists "
                    "in the local issuer history."
                ),
                "comparison.no_change": "No substantive wording change detected",
                "comparison.no_change_note": (
                    "Date and fiscal-quarter roll-forwards are treated as routine updates. "
                    "Referenced exhibits may still contain detail outside the cached "
                    "primary document."
                ),
                "context.eyebrow": "COMPANY-SPECIFIC CONTEXT",
                "context.title": "Recent company coverage",
                "context.intro": (
                    "Only headlines matched to this ticker appear here. They add context but are "
                    "not used to calculate returns or filing reactions."
                ),
                "context.refreshed": "Refreshed",
                "context.read_source": "Read source ↗",
                "context.status_available": "Available",
                "context.status_empty": "Empty",
                "context.status_stale": "Stale cache",
                "context.status_not_configured": "Not configured",
                "citation.metric": "Calculated metric",
                "citation.source": "Source passage",
                "footer.tagline": "Understand the evidence before forming a view.",
                "footer.how": "How to read this lens",
                "performance.returns": "{ticker}: {asset}; {benchmark}: {market} cumulative return",
                "performance.relative": "Return gap vs {benchmark}: {value} percentage points",
                "performance.benchmark_ending": "{benchmark} ending value",
                "benchmark.definition.SPY": (
                    "SPY tracks the S&P 500: use it to compare this stock with large US "
                    "companies over the same period."
                ),
                "benchmark.definition.QQQ": (
                    "QQQ tracks the Nasdaq-100: the 100 largest non-financial companies "
                    "listed on Nasdaq. It leans toward technology but is not a pure "
                    "technology index."
                ),
                "benchmark.matched": (
                    "Matched trading dates {start} — {end}, {sessions} sessions."
                ),
                "benchmark.partial": (
                    "Shorter than {period}: shared history starts {start}, not "
                    "{requested}. Earlier dates are not filled."
                ),
                "benchmark.fixed_elsewhere": (
                    "Only this section uses {selected}. The one-minute brief, filing "
                    "reactions and AI answers stay on {benchmark}."
                ),
                "benchmark.unavailable.missing_prices": (
                    "{selected} prices are not in this snapshot, so the comparison is off."
                ),
                "benchmark.unavailable.stale_prices": (
                    "{selected} prices end before this company's prices, so the "
                    "comparison is off until market data is refreshed."
                ),
                "benchmark.unavailable.insufficient_overlap": (
                    "Not enough shared trading dates with {selected} for this period."
                ),
                "performance.not_available": "Not available",
                "performance.not_recovered": "not recovered within the selected period",
                "performance.recovered": "recovered after {sessions} trading sessions",
                "performance.risk_title": "Experienced risk",
                "performance.risk_copy": (
                    "The largest decline was {asset} versus {benchmark_drawdown} for "
                    "{benchmark}, reaching its trough on {date}; it {recovery}."
                ),
                "ask.models_ready": "{count} validated model{suffix} available",
                "ask.models_unavailable": "Live models unavailable",
                "ask.not_configured": "Live Q&A is not configured",
                "ask.not_configured_status": (
                    "Live Q&A is not configured; all page evidence remains available."
                ),
                "ask.offline": "Unable to check live models. The page evidence remains available.",
                "ask.reading": "Reading the bounded evidence packet…",
                "ask.waiting": "Waiting for the selected model…",
                "ask.answer_failed": "The answer could not be generated.",
                "ask.selected_unavailable": "The selected model is unavailable.",
                "ask.withheld": "No unvalidated answer was shown.",
                "ask.stop": "Stop",
                "ask.stopped": (
                    "Stopped waiting. The request may still finish on the server, "
                    "but no answer will be shown."
                ),
                "ask.stopped_status": "Stopped before an answer returned.",
                "ask.validated_answer": "CITATION & FORMAT CHECK PASSED",
                "ask.answered_at": "answered {time}",
                "ask.evidence_through": "evidence through {date}",
                "ask.limitations": "What this answer cannot establish",
            },
            "zh": {
                "profile.prices": "行情区间",
                "profile.filings": "快照包含 {count} 份近期披露",

                "reaction.first_session": "首个符合条件的交易日",
                "reaction.less": "减去",
                "reaction.versus": "相对",
                "footer.universe": "公司范围：当前大型公司的便利样本，并非历史时点的指数成分",
                "footer.snapshot": "快照版本",
                "footer.market": "行情截至",
                "footer.sources": "SEC 披露 + 复权日线行情",
                "ask.original_language": "回答正文保留生成时的语言。如需中文回答，请选择中文后重新提问。",

                "nav.earnings": "财报变化",
                "nav.what": "项目介绍",
                "nav.research": "审计方法",
                "nav.find": "查找公司",
                "nav.overview": "概览",
                "nav.ask": "问 AI",
                "nav.history": "历史表现",
                "nav.filings": "公司披露",
                "nav.company_news": "公司新闻",
                "nav.trust": "基于证据，不做预测",
                "workspace.eyebrow": "本页目录",
                "workspace.title": "先读一分钟摘要，再核验下方证据。",
                "hero.eyebrow": "公司概览 · 有据可查",
                "hero.latest_close": "最新复权收盘价",
                "hero.observed": "观测日期",
                "brief.eyebrow": "一分钟概览",
                "brief.title": "这页最值得关注的内容",
                "brief.intro": (
                    "先看最新披露、历史体验和证据边界。多年财务趋势和价格隐含预期尚未接入。"
                ),
                "brief.latest_disclosure": "最新 SEC 披露",
                "brief.selected_period": "所选历史期间",
                "brief.total_return": "累计回报",
                "brief.max_drawdown": "最大回撤",
                "brief.period_context": "的复权日线数据，对比 {benchmark}。仅作历史背景，不代表预测。",
                "brief.explore_history": "查看完整历史 ↓",
                "brief.explore_filings": "阅读披露证据 ↓",
                "brief.boundary": "证据边界：",
                "brief.metric_revenue": "营业收入",
                "brief.metric_gross_margin": "毛利率",
                "brief.metric_operating_margin": "营业利润率",
                "brief.metric_free_cash_flow": "自由现金流",
                "brief.metric_fcf_per_share": "每股自由现金流",
                "brief.metric_diluted_shares": "稀释股本",
                "brief.metric_share_change": "稀释股本变动",
                "brief.trend_up": "上升",
                "brief.trend_down": "下降",
                "brief.trend_flat": "大致持平",
                "brief.coverage_complete": "完整",
                "brief.coverage_partial": "部分",
                "brief.coverage_missing": "缺失",
                "reaction.building_history": "历史样本仍在积累",
                "reaction.more_extreme": "比 {pct} 的历史样本更极端",
                "reaction.history_note_building": (
                    "已有 {count} 次可测算披露{suffix}；满 5 次后显示分位"
                ),
                "reaction.history_note_extreme": "基于此前 {count} 次可测算披露",
                "reaction.unavailable_move": "暂无法测算市场反应",
                "reaction.missing_session_bars": "所需交易日行情未同时缓存",
                "timeline.title": "近期披露时间线",
                "timeline.subtitle": "披露何时到达，以及下一可交易日如何变动",
                "timeline.range": "由旧到新 · 最近 {count} 条",
                "timeline.boundary": (
                    "相对变动为公司开盘至收盘收益减去 {benchmark}；这是历史背景，不是事件预测。"
                ),
                "filing.reaction_not_measurable": "市场反应尚不可测算",
                "item.1.01": "签署重大协议",
                "item.1.02": "终止重大协议",
                "item.1.03": "破产或接管",
                "item.2.01": "资产收购或处置",
                "item.2.02": "经营业绩(财报)",
                "item.2.03": "产生直接财务义务",
                "item.2.04": "触发义务加速事件",
                "item.2.05": "退出或处置成本",
                "item.2.06": "重大减值",
                "item.3.01": "退市或上市规则问题",
                "item.3.02": "未注册股权出售",
                "item.3.03": "重大修改证券持有人权利",
                "item.4.01": "更换审计师",
                "item.4.02": "此前财务报表不可靠",
                "item.5.01": "控制权变更",
                "item.5.02": "董事或主要高管变更",
                "item.5.03": "财年或章程修订",
                "item.5.07": "股东投票结果",
                "item.7.01": "Regulation FD 披露",
                "item.8.01": "其他事项",
                "item.9.01": "财务报表与附件",
                "item.other": "其他披露",
                "explain.no_filing": "本地数据集中没有该公司的披露。",
                "ask.task_quality": "经营质量",
                "ask.task_cash": "盈利与现金",
                "ask.task_capital": "每股资本",
                "ask.task_thesis": "论点风险",
                "ask.task_missing": "缺失证据",
                "ask.task_quality_title": "审视多年经营质量",
                "ask.task_quality_copy": "使用带来源链接的年度收入、利润率、每股自由现金流和稀释股本。",
                "ask.task_quality_question": (
                    "仅依据年度基本面证据，收入、毛利率、营业利润率、每股自由现金流和稀释股本"
                    "在可获得的财政年度里如何变化？"
                ),
                "ask.task_cash_title": "比较盈利与现金质量",
                "ask.task_cash_copy": "使用净利润、经营现金流、自由现金流及转化率。",
                "ask.task_cash_question": (
                    "经营现金流、自由现金流和现金转化率，对最近可比财政年度的盈利质量说明了什么？"
                ),
                "ask.task_capital_title": "检查每股资本配置",
                "ask.task_capital_copy": "使用稀释股本、每股自由现金流，以及已有的回购与分红证据。",
                "ask.task_capital_question": (
                    "稀释股本和每股自由现金流如何变化？现有证据中有哪些资本回报信息？"
                ),
                "ask.task_thesis_title": "找出论点风险",
                "ask.task_thesis_copy": "使用披露段落、市场反应背景和基本面覆盖缺口。",
                "ask.task_thesis_question": (
                    "哪些被引用的披露、市场反应或基本面缺口，最明显地挑战长期经营论点？"
                ),
                "ask.task_missing_title": "列出缺失证据",
                "ask.task_missing_copy": "使用解释边界和基本面覆盖状态。",
                "ask.task_missing_question": (
                    "若要判断经营质量、现金质量或每股价值创造，本页还缺少哪些重要证据？"
                ),
                "mode.grounded": "来源受限的 AI",
                "mode.fallback": "基于来源的摘要",
                "mode.unavailable": "暂无解释",
                "signal.eyebrow": "本次披露 vs 该公司自身历史",
                "signal.title": "对这家公司来说，这次不寻常吗？",
                "signal.intro": ("这里的每个数字都只把本次披露和同一家公司的历史披露相比，"
                    "不与其他公司比较，也不构成对股价方向的判断。"),
                "signal.why": "依据",
                "signal.boundary": ("这里估计的是反应可能有多大，不是方向。"
                    "它是阅读优先级，不是投资建议。"),
                "signal.probability": "出现异常大反应的概率",
                "signal.base": "该公司历史上越过自身标准的频率",
                "signal.history": "作为比较基础的历史披露数",
                "signal.chart_x": "语言异常度 \u2192",
                "signal.chart_y": "\u2191 反应幅度",
                "signal.state.read_now": "立即阅读",
                "signal.state.monitor": "保持关注",
                "signal.state.routine": "例行披露",
                "signal.state.insufficient_history": "历史不足",
                "signal.state.withheld": "已扣留",
                "nav.signal": "本次披露",
                "nav.volatility": "预计区间",
                "vol.eyebrow": "未来 {count} 个交易日",
                "vol.title": "预计波动区间有多宽",
                "vol.intro": ("未来一个月这只股票预计会有多大幅度的波动，给出的是一个区间"
                    "而不是一个数字。它不说明方向——区间宽既可能是好消息，也可能是坏消息。"),
                "vol.median": "最可能的年化波动率",
                "vol.band": "80% 的情况落在这个区间",
                "vol.usual": "该公司自身的常态水平",
                "vol.state.typical_for_this_issuer": "与该公司常态相当",
                "vol.state.slightly_elevated": "略高于常态",
                "vol.state.elevated": "明显高于常态",
                "vol.state.unusually_calm": "异常平静",
                "ask.eyebrow": "关于这家公司的问题",
                "ask.title": "你想了解这家公司的什么？",
                "ask.validated": "检查引用与回答格式",
                "ask.intro": (
                    "先选择一个引导式研究任务，检查自动生成的问题，再决定是否发送。"
                    "模型只能使用本页冻结的证据。"
                ),
                "ask.advanced": "模型、回答语言与资料范围",
                "ask.more_tasks": "更多研究问题",
                "ask.model": "模型",
                "ask.evidence_scope": "证据范围",
                "ask.loading_scopes": "正在载入范围…",
                "ask.scope_core": "核心财务",
                "ask.scope_company": "公司动态",
                "ask.scope_market": "市场背景",
                "ask.scope_all": "全部证据",
                "ask.scope_note_core": "仅 SEC 备案与长期基本面。",
                "ask.scope_note_company": "核心财务,加上该公司的近期新闻。",
                "ask.scope_note_market": "核心财务,加上行业与宏观新闻。",
                "ask.scope_note_all": "核心财务、公司动态与市场背景的组合。",
                "ask.loading_models": "正在读取可用模型…",
                "ask.answer_language": "回答语言",
                "ask.question": "问题",
                "ask.placeholder": "最新一份 8-K 披露了什么？",
                "ask.choose_task": "选择要研究的问题",
                "ask.choose_task_copy": "选择标签会生成一个受限问题，但不会自动发送。",
                "ask.task_filing": "最新披露",
                "ask.task_history": "历史表现对比",
                "ask.task_risk": "实际风险",
                "ask.task_limits": "证据边界",
                "ask.guided_prompt": "引导式问题",
                "ask.review_question": "检查或修改生成的问题",
                "ask.review_question_copy": "发送前由你最终确认。",
                "ask.task_filing_title": "解释最新公司披露",
                "ask.task_filing_copy": "使用最新缓存的 8-K、提取事实和来源段落。",
                "ask.task_filing_question": "最新一份 8-K 说了什么？哪些引用段落支持这个回答？",
                "ask.task_history_title": "比较历史表现",
                "ask.task_history_copy": "使用所选期间的计算回报，并按相同日期与 {benchmark} 比较。",
                "ask.task_history_question": (
                    "在所选历史期间，{ticker} 相对 {benchmark} 的表现如何？"
                ),
                "ask.task_risk_title": "解释实际发生过的风险",
                "ask.task_risk_copy": "使用回撤、波动率、最差单日、Beta 和修复时间指标。",
                "ask.task_risk_question": (
                    "所选期间内 {ticker} 经历了哪些风险？这些历史指标不能预测什么？"
                ),
                "ask.task_limits_title": "审查证据边界",
                "ask.task_limits_copy": "说明缓存了什么、缺少什么，以及本页无法证明什么。",
                "ask.task_limits_question": (
                    "目前包含和排除了哪些证据？哪些结论无法得到支持？"
                ),
                "ask.submit": "获取带来源的回答",
                "ask.retry": "重新检查模型",
                "ask.checking_models": "正在检查可用模型…",
                "ask.scope_title": "这个演示可以回答什么",
                "ask.in_scope": "可以回答",
                "ask.in_scope_1": "最新 8-K 说了什么，并提供引用段落",
                "ask.in_scope_2": "相对 {benchmark}（本快照固定基准）的历史回报和风险；历史区切换到其他基准时也不变",
                "ask.in_scope_3": "披露后的观测反应和历史措辞变化",
                "ask.in_scope_4": "当前有哪些证据、缺少哪些证据",
                "ask.out_scope": "始终拦截",
                "ask.out_scope_1": "买入、卖出或持有建议",
                "ask.out_scope_2": "目标价格和未来预测",
                "ask.out_scope_3": "无引用事实或虚构数字",
                "ask.out_scope_4": "超出冻结证据包的结论",
                "ask.control_flow": "生成问题 → 受限证据 → 模型 → 校验器 → 带引用答案",
                "ask.boundary": (
                    "范围：解释而非推荐 · 问题最多 280 字符 · 公开演示限流 · API 密钥只在服务端"
                ),
                "performance.eyebrow": "长期历史表现",
                "performance.title": "投入 10,000 美元后发生了什么？",
                "performance.intro": (
                    "按完全相同日期比较复权持有 {benchmark} 的历史结果；这是历史背景，不是"
                    "预期回报。"
                ),
                "performance.ending_value": "期末价值",
                "performance.more_risk": "展开更多风险指标",
                "metric.return": "年化回报",
                "metric.return.definition": "复合年增长率；仅为历史结果，不是预测。",
                "metric.volatility": "年化波动率",
                "metric.volatility.definition": "日收益率标准差按年化处理。",
                "metric.beta": "相对 {benchmark} 的 Beta",
                "metric.beta.definition": "对基准日收益变化的敏感度；1.0 大致表示与基准同步。",
                "metric.correlation": "相对 {benchmark} 的相关性",
                "metric.correlation.definition": "日收益共同变化的程度，范围从 -1 到 +1。",
                "metric.current_drawdown": "当前回撤",
                "metric.current_drawdown.definition": "当前复权价值低于所选期间最高点的幅度。",
                "metric.worst_day": "最差单日",
                "metric.worst_day.definition": "所选期间内最大的单日复权价格跌幅。",
                "filings.eyebrow": "公司披露解读",
                "filings.title": "近期 8-K 披露",
                "filings.latest_accepted": "最新披露接收日期",
                "filings.sec_checked": "SEC 检查日期",
                "filings.sec_collected": "SEC 缓存采集日期",
                "filings.sec_unavailable": "SEC 缓存时间不可用",
                "filings.intro": "最新披露保持展开：查看公司说了什么、下一可交易日如何变化，以及措辞是否有实质改变。",
                "filing.accepted": "SEC 接收时间",
                "filing.latest": "最新披露",
                "filing.view_evidence": "查看证据",
                "filing.source_facts": "来源段落与提取事实",
                "filing.extracted_facts": "提取到的事实",
                "filing.relevant_passages": "相关原文",
                "filing.no_local_filing": "暂无本地披露",
                "filing.evidence_unavailable": "证据暂不可用",
                "filing.no_entities": "主文档中没有带引用的实体",
                "filing.no_passages": "没有段落达到确定性相关度阈值。",
                "filing.source_record": "来源记录",
                "filing.open_sec": "打开 SEC 原文 ↗",
                "filing.source_note": "SEC 原文保持申报语言，便于逐字核验引用。",
                "reaction.title": "披露后发生了什么",
                "reaction.observed": "仅为观测，不作归因",
                "reaction.company_move": "公司股价变化",
                "reaction.open_close": "开盘到收盘",
                "reaction.after_benchmark": "扣除 {benchmark} 后",
                "reaction.compared": "与历史披露相比",
                "reaction.unavailable": "市场反应暂不可测量",
                "reaction.missing_bars": "首个符合规则的交易日缺少公司或基准行情数据。",
                "reaction.boundary": (
                    "这是 SEC 接收披露后第一个符合规则的交易日。它描述随后发生的情况，"
                    "并不声称股价变化由该披露造成。"
                ),
                "comparison.title": "与上一份同类披露相比的变化",
                "comparison.prior": "上一份披露 ↗",
                "comparison.unavailable": "暂无上一份同类披露可比较",
                "comparison.no_prior": "本地公司历史中没有相同表单和主要事件类型的更早披露。",
                "comparison.no_change": "未发现实质性措辞变化",
                "comparison.no_change_note": (
                    "日期和财季顺延会被视为常规更新；引用的附件仍可能包含缓存主文档之外的细节。"
                ),
                "context.eyebrow": "公司相关信息",
                "context.title": "近期公司报道",
                "context.intro": "这里只显示与当前股票明确匹配的标题；它们提供背景，但不参与回报或披露反应计算。",
                "context.refreshed": "更新时间",
                "context.read_source": "阅读来源 ↗",
                "context.status_available": "可用",
                "context.status_empty": "暂无内容",
                "context.status_stale": "缓存已过期",
                "context.status_not_configured": "未配置",
                "citation.metric": "计算指标",
                "citation.source": "来源段落",
                "footer.tagline": "先理解证据，再形成自己的判断。",
                "footer.how": "如何阅读 Company Lens",
                "performance.returns": "累计回报：{ticker} {asset}；{benchmark} {market}",
                "performance.relative": "本期回报差（公司减 {benchmark}）：{value} 个百分点",
                "performance.benchmark_ending": "{benchmark} 期末价值",
                "benchmark.definition.SPY": (
                    "SPY 跟踪标普 500，用来比较这只股票与美国大型公司整体在同一时期的表现。"
                ),
                "benchmark.definition.QQQ": (
                    "QQQ 跟踪纳斯达克 100 指数，即在纳斯达克上市的 100 家最大非金融公司。"
                    "它偏重科技，但不是纯科技指数。"
                ),
                "benchmark.matched": "匹配交易日 {start} — {end}，共 {sessions} 个交易日。",
                "benchmark.partial": (
                    "不足 {period}：共同历史从 {start} 开始，而非 {requested}；不会补齐更早的日期。"
                ),
                "benchmark.fixed_elsewhere": (
                    "只有本区使用 {selected}。一分钟摘要、披露反应和 AI 回答仍以 {benchmark} 为基准。"
                ),
                "benchmark.unavailable.missing_prices": "本快照没有 {selected} 价格，因此无法比较。",
                "benchmark.unavailable.stale_prices": (
                    "{selected} 价格早于本公司价格截止，需刷新行情后才能比较。"
                ),
                "benchmark.unavailable.insufficient_overlap": "该期间与 {selected} 的共同交易日不足。",
                "performance.not_available": "暂无数据",
                "performance.not_recovered": "在所选期间内尚未收复",
                "performance.recovered": "在 {sessions} 个交易日后收复",
                "performance.risk_title": "实际经历的风险",
                "performance.risk_copy": (
                    "最大跌幅为 {asset}，同期 {benchmark} 为 {benchmark_drawdown}；最低点出现在 "
                    "{date}，此后{recovery}。"
                ),
                "ask.models_ready": "已有 {count} 个通过校验的模型可用",
                "ask.models_unavailable": "实时模型暂不可用",
                "ask.not_configured": "线上问答尚未配置",
                "ask.not_configured_status": "线上问答尚未配置；页面证据仍可阅读。",
                "ask.offline": "无法检查可用模型。页面证据仍可阅读。",
                "ask.reading": "正在读取受限证据包…",
                "ask.waiting": "正在等待所选模型…",
                "ask.answer_failed": "暂时无法生成答案。",
                "ask.selected_unavailable": "所选模型暂不可用。",
                "ask.withheld": "未展示任何未经校验的答案。",
                "ask.stop": "停止",
                "ask.stopped": "已停止等待。该请求可能仍在服务端完成，但不会展示任何答案。",
                "ask.stopped_status": "已在返回答案前停止。",
                "ask.validated_answer": "引用与格式检查通过",
                "ask.answered_at": "{time} 生成",
                "ask.evidence_through": "证据截至 {date}",
                "ask.limitations": "这个答案无法证明什么",
            },
        },
        ensure_ascii=False,
    )
    return f"""
const periods = JSON.parse(document.getElementById('period-data').textContent);
const ticker = {json.dumps(ticker)};
const benchmark = {json.dumps(benchmark)};
// The history section may compare against another benchmark; everything else
// (brief, filing reactions, AI request) stays on `benchmark`.
const comparisons = JSON.parse(document.getElementById('benchmark-data').textContent);
let historyBenchmark = benchmark;
const translations = {translations};
const svg = document.getElementById('growth-chart');
const assetPath = document.getElementById('asset-path');
const benchmarkPath = document.getElementById('benchmark-path');
const hoverLine = document.getElementById('hover-line');
const assetPoint = document.getElementById('asset-point');
const benchmarkPoint = document.getElementById('benchmark-point');
const tooltip = document.getElementById('chart-tooltip');
let currentGrowth = [];
let chartScale = null;
let currentPeriod = {json.dumps(default_period)};
let uiLanguage = 'en';

function tr(key, values={{}}) {{
  const template = (translations[uiLanguage] || translations.en)[key] || translations.en[key] || key;
  return Object.entries(values).reduce(
    (copy, [name, value]) => copy.replaceAll(`{{${{name}}}}`, String(value)),
    template,
  );
}}

function storedLanguage() {{
  try {{ return window.localStorage.getItem('company-lens-language'); }} catch (error) {{ return null; }}
}}

function applyLanguage(language, persist=true) {{
  uiLanguage = language === 'zh' ? 'zh' : 'en';
  document.documentElement.lang = uiLanguage === 'zh' ? 'zh-CN' : 'en';
  document.querySelectorAll('[data-i18n], [data-i18n-en]').forEach(element => {{
    if (element.dataset.i18nEn || element.dataset.i18nZh) {{
      element.textContent = uiLanguage === 'zh'
        ? (translations.zh[element.dataset.i18n] || element.dataset.i18nZh || element.dataset.i18nEn || element.textContent)
        : (element.dataset.i18nEn || element.textContent);
      return;
    }}
    const values = {{
      ticker,
      benchmark: scopedBenchmark(element),
      count: element.dataset.i18nCount || '',
      suffix: element.dataset.i18nSuffix || '',
      pct: element.dataset.i18nPct || '',
    }};
    element.textContent = tr(element.dataset.i18n, values);
  }});
  document.querySelectorAll('[data-i18n-placeholder]').forEach(element => {{
    element.placeholder = tr(element.dataset.i18nPlaceholder, {{ticker, benchmark}});
  }});
  document.querySelectorAll('[data-i18n-title]').forEach(element => {{
    element.title = tr(element.dataset.i18nTitle, {{ticker, benchmark: scopedBenchmark(element)}});
  }});
  document.querySelectorAll('[data-freshness-key]').forEach(element => {{
    const date = element.dataset.freshnessDate;
    element.textContent = `${{tr(element.dataset.freshnessKey)}}${{date ? ` ${{date}}` : ''}}`;
  }});
  const modeBadge = document.querySelector('[data-explanation-mode]');
  const modeKey = modeBadge.dataset.explanationMode === 'grounded_llm'
    ? 'mode.grounded'
    : modeBadge.dataset.explanationMode === 'deterministic_fallback'
      ? 'mode.fallback'
      : 'mode.unavailable';
  modeBadge.textContent = tr(modeKey);
  const toggle = document.getElementById('language-toggle');
  toggle.textContent = uiLanguage === 'zh' ? 'EN' : '中文';
  toggle.setAttribute('aria-label', uiLanguage === 'zh' ? 'Switch to English' : '切换为中文');
  toggle.setAttribute('aria-pressed', String(uiLanguage === 'zh'));
  document.getElementById('ask-language').value = uiLanguage === 'zh' ? 'Chinese' : 'English';
  refreshAskStatus();
  refreshAskAnswerMeta();
  refreshLocalizedDetails();
  if (askModel.options.length && (askModel.dataset.state === 'unavailable' || askModel.dataset.state === 'not_configured')) {{
    askModel.options[0].textContent = tr(
      askModel.dataset.state === 'not_configured' ? 'ask.not_configured' : 'ask.models_unavailable',
    );
  }}
  refreshAskTask();
  if (persist) {{
    try {{ window.localStorage.setItem('company-lens-language', uiLanguage); }} catch (error) {{}}
  }}
  setPeriod(currentPeriod);
}}

const money = value => new Intl.NumberFormat('en-US', {{style:'currency',currency:'USD',maximumFractionDigits:0}}).format(value);
const pct = value => new Intl.NumberFormat('en-US', {{style:'percent',maximumFractionDigits:1,signDisplay:'exceptZero'}}).format(value);
const plainPct = value => new Intl.NumberFormat('en-US', {{style:'percent',maximumFractionDigits:1}}).format(value);
const decimal = value => value == null ? tr('performance.not_available') : value.toFixed(2);

function scopedBenchmark(element) {{
  return element.closest('[data-benchmark-scope="history"]') ? historyBenchmark : benchmark;
}}

function periodLabel(label) {{
  return uiLanguage === 'zh' ? label.replace('Y', ' 年') : label;
}}

function historyView(symbol, label) {{
  if (symbol === benchmark) return periods[label];
  const view = comparisons[symbol] && comparisons[symbol].periods[label];
  return view && view.status === 'available' ? view : null;
}}

function setBenchmark(symbol) {{
  const comparison = comparisons[symbol];
  if (symbol !== benchmark && (!comparison || comparison.status !== 'available')) return;
  historyBenchmark = symbol;
  const label = historyView(symbol, currentPeriod)
    ? currentPeriod
    : Object.keys(periods).find(candidate => historyView(symbol, candidate));
  setPeriod(label);
}}

function setPeriod(label) {{
  if (!historyView(historyBenchmark, label)) return;
  currentPeriod = label;
  const brief = periods[label].performance;
  document.getElementById('brief-period-label').textContent = periodLabel(label);
  document.getElementById('total-return').textContent = pct(brief.asset.total_return);
  document.getElementById('max-drawdown').textContent = plainPct(brief.asset.max_drawdown);
  renderHistory(label);
}}

function renderHistory(label) {{
  const selected = historyBenchmark;
  const view = historyView(selected, label);
  const p = view.performance;
  document.querySelectorAll('.period-button').forEach(button => {{
    const period = button.dataset.period;
    const active = period === label;
    const usable = Boolean(historyView(selected, period));
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
    button.disabled = !usable;
    button.title = usable ? '' : tr('benchmark.unavailable.insufficient_overlap', {{selected}});
    button.textContent = periodLabel(period);
  }});
  document.querySelectorAll('.benchmark-button').forEach(button => {{
    const symbol = button.dataset.benchmark;
    const active = symbol === selected;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
    const reason = button.dataset.unavailableReason;
    button.title = button.disabled && reason
      ? tr(`benchmark.unavailable.${{reason}}`, {{selected: symbol}})
      : '';
  }});
  document.querySelectorAll('#performance [data-i18n]').forEach(element => {{
    element.textContent = tr(element.dataset.i18n, {{ticker, benchmark: selected}});
  }});
  document.querySelectorAll('#performance [data-i18n-title]').forEach(element => {{
    element.title = tr(element.dataset.i18nTitle, {{ticker, benchmark: selected}});
  }});
  document.getElementById('legend-benchmark').textContent = selected;
  const definition = document.getElementById('benchmark-definition');
  if (translations.en[`benchmark.definition.${{selected}}`]) {{
    definition.textContent = tr(`benchmark.definition.${{selected}}`);
  }}
  const notes = [tr('benchmark.matched', {{
    start: view.coverage ? view.coverage.start : view.period.start,
    end: view.coverage ? view.coverage.end : view.period.end,
    sessions: p.observations,
  }})];
  if (view.coverage && view.coverage.status === 'partial') {{
    notes.push(tr('benchmark.partial', {{
      period: periodLabel(label), start: view.coverage.start, requested: view.coverage.requested_start,
    }}));
  }}
  if (selected !== benchmark) notes.push(tr('benchmark.fixed_elsewhere', {{selected, benchmark}}));
  const unavailable = Array.from(document.querySelectorAll('.benchmark-button:disabled'))
    .map(button => tr(`benchmark.unavailable.${{button.dataset.unavailableReason}}`, {{selected: button.dataset.benchmark}}));
  document.getElementById('benchmark-note').textContent = [...notes, ...unavailable].join(' ');
  document.getElementById('benchmark-ending-label').textContent = tr(
    'performance.benchmark_ending', {{benchmark: selected}},
  );
  document.getElementById('ending-value').textContent = money(p.ending_value);
  document.getElementById('benchmark-ending').textContent = money(p.initial_investment * (1 + p.benchmark.total_return));
  document.getElementById('history-return-comparison').textContent = tr('performance.returns', {{
    ticker, asset: pct(p.asset.total_return), market: pct(p.benchmark.total_return), benchmark: selected,
  }});
  document.getElementById('relative-copy').textContent = tr('performance.relative', {{
    value: `${{(p.relative_total_return * 100).toFixed(1)}}`, benchmark: selected,
  }});
  document.getElementById('cagr').textContent = pct(p.asset.cagr);
  document.getElementById('volatility').textContent = plainPct(p.asset.annualized_volatility);
  document.getElementById('beta').textContent = decimal(p.beta);
  document.getElementById('correlation').textContent = decimal(p.correlation);
  document.getElementById('current-drawdown').textContent = plainPct(p.asset.current_drawdown);
  document.getElementById('worst-day').textContent = plainPct(p.asset.worst_day);
  const recovery = p.asset.recovery_sessions == null
    ? tr('performance.not_recovered')
    : tr('performance.recovered', {{sessions: p.asset.recovery_sessions}});
  const riskNote = document.getElementById('risk-note');
  riskNote.replaceChildren();
  const riskTitle = document.createElement('strong');
  riskTitle.textContent = tr('performance.risk_title');
  const riskCopy = document.createElement('span');
  riskCopy.textContent = tr('performance.risk_copy', {{
    asset: plainPct(p.asset.max_drawdown),
    benchmark_drawdown: plainPct(p.benchmark.max_drawdown),
    benchmark: selected,
    date: p.asset.max_drawdown_date,
    recovery,
  }});
  riskNote.append(riskTitle, riskCopy);
  document.getElementById('chart-range').textContent = `${{view.period.start}} — ${{view.period.end}}`;
  drawChart(view.growth);
}}

function drawChart(growth) {{
  currentGrowth = growth;
  const left=58, right=896, top=22, bottom=316;
  const values = growth.flatMap(row => [row.asset_value,row.benchmark_value]);
  let min = Math.min(...values), max = Math.max(...values);
  const pad = Math.max((max-min)*0.12, 500); min=Math.max(0,min-pad); max+=pad;
  const x = index => left + (index / Math.max(growth.length-1,1)) * (right-left);
  const y = value => bottom - ((value-min)/(max-min))*(bottom-top);
  const path = key => growth.map((row,index) => `${{index?'L':'M'}}${{x(index).toFixed(1)}},${{y(row[key]).toFixed(1)}}`).join(' ');
  assetPath.setAttribute('d', path('asset_value'));
  benchmarkPath.setAttribute('d', path('benchmark_value'));
  const grid = [], labels=[];
  for(let i=0;i<5;i++){{ const value=min+(max-min)*i/4, yy=y(value); grid.push(`<line x1="${{left}}" x2="${{right}}" y1="${{yy}}" y2="${{yy}}"></line>`); labels.push(`<text x="${{left-10}}" y="${{yy+4}}" text-anchor="end">${{money(value)}}</text>`); }}
  labels.push(`<text x="${{left}}" y="344">${{growth[0].date}}</text><text x="${{right}}" y="344" text-anchor="end">${{growth[growth.length-1].date}}</text>`);
  document.getElementById('chart-grid').innerHTML=grid.join('');
  document.getElementById('chart-labels').innerHTML=labels.join('');
  chartScale={{left,right,top,bottom,x,y}};
  hideTooltip();
}}

function hideTooltip() {{ tooltip.classList.remove('visible'); hoverLine.style.opacity=0; assetPoint.style.opacity=0; benchmarkPoint.style.opacity=0; }}
svg.addEventListener('pointermove', event => {{
  if(!chartScale || !currentGrowth.length) return;
  const rect=svg.getBoundingClientRect(), svgX=(event.clientX-rect.left)*920/rect.width;
  const ratio=Math.max(0,Math.min(1,(svgX-chartScale.left)/(chartScale.right-chartScale.left)));
  const index=Math.round(ratio*(currentGrowth.length-1)), row=currentGrowth[index], xx=chartScale.x(index);
  hoverLine.setAttribute('x1',xx); hoverLine.setAttribute('x2',xx); hoverLine.style.opacity=1;
  assetPoint.setAttribute('cx',xx); assetPoint.setAttribute('cy',chartScale.y(row.asset_value)); assetPoint.style.opacity=1;
  benchmarkPoint.setAttribute('cx',xx); benchmarkPoint.setAttribute('cy',chartScale.y(row.benchmark_value)); benchmarkPoint.style.opacity=1;
  tooltip.innerHTML=`<b>${{row.date}}</b><span>${{ticker}} ${{money(row.asset_value)}}</span><span>${{historyBenchmark}} ${{money(row.benchmark_value)}}</span>`;
  tooltip.style.left=`${{Math.min(Math.max(event.clientX-rect.left,90),rect.width-90)}}px`; tooltip.classList.add('visible');
}});
svg.addEventListener('pointerleave', hideTooltip);
document.querySelectorAll('.period-button').forEach(button => button.addEventListener('click',()=>setPeriod(button.dataset.period)));
document.querySelectorAll('.benchmark-button').forEach(button => button.addEventListener('click',()=>setBenchmark(button.dataset.benchmark)));
setPeriod({json.dumps(default_period)});

const askForm = document.getElementById('ask-form');
const askModel = document.getElementById('ask-model');
const askLanguage = document.getElementById('ask-language');
const askScope = document.getElementById('ask-scope');
const askScopeNote = document.getElementById('ask-scope-note');
const askQuestion = document.getElementById('ask-question');
const askSubmit = document.getElementById('ask-submit');
const askStop = document.getElementById('ask-stop');
const askRetry = document.getElementById('ask-retry');
// The in-flight request, so the visitor can stop waiting on it. Aborting is
// honest about what it does and does not do: it drops the browser's side of the
// call and guarantees no answer is rendered, but the provider request is
// already away and may still complete and still be billed. The stopped message
// says so rather than implying a refund.
let askController = null;
const askStatus = document.getElementById('ask-status');
const askResult = document.getElementById('ask-result');
const askTaskTitle = document.getElementById('ask-task-title');
const askTaskDescription = document.getElementById('ask-task-description');
const askTaskTabs = Array.from(document.querySelectorAll('[data-ask-task]'));
const askTaskDefinitions = {{
  filing: {{
    title: 'ask.task_filing_title',
    copy: 'ask.task_filing_copy',
    question: 'ask.task_filing_question',
  }},
  history: {{
    title: 'ask.task_history_title',
    copy: 'ask.task_history_copy',
    question: 'ask.task_history_question',
  }},
  risk: {{
    title: 'ask.task_risk_title',
    copy: 'ask.task_risk_copy',
    question: 'ask.task_risk_question',
  }},
  limits: {{
    title: 'ask.task_limits_title',
    copy: 'ask.task_limits_copy',
    question: 'ask.task_limits_question',
  }},
  quality: {{
    title: 'ask.task_quality_title',
    copy: 'ask.task_quality_copy',
    question: 'ask.task_quality_question',
  }},
  cash: {{
    title: 'ask.task_cash_title',
    copy: 'ask.task_cash_copy',
    question: 'ask.task_cash_question',
  }},
  capital: {{
    title: 'ask.task_capital_title',
    copy: 'ask.task_capital_copy',
    question: 'ask.task_capital_question',
  }},
  thesis: {{
    title: 'ask.task_thesis_title',
    copy: 'ask.task_thesis_copy',
    question: 'ask.task_thesis_question',
  }},
  missing: {{
    title: 'ask.task_missing_title',
    copy: 'ask.task_missing_copy',
    question: 'ask.task_missing_question',
  }},
}};
let activeAskTask = 'filing';
let lastGuidedQuestion = '';

function refreshAskTask(forceQuestion=false) {{
  const definition = askTaskDefinitions[activeAskTask] || askTaskDefinitions.filing;
  const values = {{ticker, benchmark}};
  const nextQuestion = tr(definition.question, values);
  const shouldReplace = forceQuestion
    || !askQuestion.value.trim()
    || askQuestion.value === lastGuidedQuestion;
  askTaskTitle.textContent = tr(definition.title, values);
  askTaskDescription.textContent = tr(definition.copy, values);
  askTaskTabs.forEach(tab => {{
    const active = tab.dataset.askTask === activeAskTask;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', String(active));
    tab.tabIndex = active ? 0 : -1;
  }});
  if (shouldReplace) askQuestion.value = nextQuestion;
  lastGuidedQuestion = nextQuestion;
}}

function selectAskTask(task, focusQuestion=true) {{
  if (!askTaskDefinitions[task]) return;
  activeAskTask = task;
  refreshAskTask(true);
  if (focusQuestion) askQuestion.focus();
}}

function setAskStatus(message, state='') {{
  askStatus.textContent = message;
  askStatus.className = state;
  askStatus.dataset.statusKey = '';
  askStatus.dataset.statusValues = '';
}}

function setTranslatedAskStatus(key, values={{}}, state='') {{
  askStatus.dataset.statusKey = key;
  askStatus.dataset.statusValues = JSON.stringify(values);
  askStatus.textContent = tr(key, values);
  askStatus.className = state;
}}

function refreshAskStatus() {{
  const key = askStatus.dataset.statusKey;
  if (!key) return;
  let values = {{}};
  try {{ values = JSON.parse(askStatus.dataset.statusValues || '{{}}'); }} catch (error) {{}}
  askStatus.textContent = tr(key, values);
}}

// The server is the authority on which scopes exist -- the page renders what it
// is told rather than hard-coding a list that could drift out of step with the
// evidence actually bundled. Labels are looked up in the page dictionary so the
// selector follows the language toggle; the server's own label is the fallback.
function populateAskScopes(scopes, defaultScope) {{
  const available = Array.isArray(scopes) ? scopes : [];
  askScope.replaceChildren();
  if (!available.length) {{
    askScope.disabled = true;
    askScopeNote.hidden = true;
    return;
  }}
  available.forEach(scope => {{
    const option = document.createElement('option');
    option.value = scope.id;
    option.dataset.i18n = `ask.scope_${{scope.id}}`;
    option.textContent = tr(`ask.scope_${{scope.id}}`) || scope.label || scope.id;
    askScope.append(option);
  }});
  const preferred = defaultScope || available[0].id;
  askScope.value = available.some(scope => scope.id === preferred)
    ? preferred : available[0].id;
  askScope.disabled = false;
  askScopeNote.hidden = false;
  refreshAskScopeNote();
}}

function refreshAskScopeNote() {{
  if (!askScope.value) return;
  const key = `ask.scope_note_${{askScope.value}}`;
  askScopeNote.dataset.i18n = key;
  askScopeNote.textContent = tr(key);
}}

askScope.addEventListener('change', refreshAskScopeNote);

async function loadAskModels() {{
  askRetry.hidden = true;
  try {{
    const response = await fetch('/api/ask', {{headers: {{Accept: 'application/json'}}}});
    if (!response.ok) throw new Error('network');
    const payload = await response.json();
    const models = Array.isArray(payload.models) ? payload.models : [];
    populateAskScopes(payload.scopes, payload.default_scope);
    askModel.replaceChildren();
    if (!models.length) {{
      const option = document.createElement('option');
      option.textContent = tr('ask.not_configured');
      askModel.append(option);
      askModel.dataset.state = 'not_configured';
      askModel.disabled = true;
      askSubmit.disabled = true;
      setTranslatedAskStatus('ask.not_configured_status', {{}}, 'notice');
      return;
    }}
    models.forEach(model => {{
      const option = document.createElement('option');
      option.value = model.id;
      option.textContent = `${{model.provider}} · ${{model.model}}`;
      askModel.append(option);
    }});
    askModel.dataset.state = 'ready';
    askModel.disabled = false;
    askSubmit.disabled = false;
    setTranslatedAskStatus('ask.models_ready', {{
      count: models.length,
      suffix: models.length === 1 ? '' : 's',
    }}, 'ready');
  }} catch (error) {{
    askModel.replaceChildren();
    const option = document.createElement('option');
    option.textContent = tr('ask.models_unavailable');
    askModel.append(option);
    askModel.dataset.state = 'unavailable';
    askModel.disabled = true;
    askSubmit.disabled = true;
    askRetry.hidden = false;
    // A static preview has no function to ask, so the scope picker has nothing
    // to offer. Empty it rather than leaving "Loading scopes…" on screen
    // forever, which reads as a hang rather than as an absent backend.
    populateAskScopes([], null);
    setTranslatedAskStatus('ask.offline', {{}}, 'error');
  }}
}}

askRetry.addEventListener('click', loadAskModels);

askTaskTabs.forEach((tab, index) => {{
  tab.addEventListener('click', () => selectAskTask(tab.dataset.askTask));
  tab.addEventListener('keydown', event => {{
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const direction = event.key === 'ArrowRight' ? 1 : -1;
    const nextIndex = (index + direction + askTaskTabs.length) % askTaskTabs.length;
    const next = askTaskTabs[nextIndex];
    const fold = next.closest('details');
    if (fold && !fold.open) fold.open = true;
    next.focus();
    selectAskTask(next.dataset.askTask, false);
  }});
}});

askStop.addEventListener('click', () => {{
  if (askController) askController.abort();
}});

askForm.addEventListener('submit', async event => {{
  event.preventDefault();
  const question = askQuestion.value.trim();
  if (!question || askModel.disabled) return;
  askSubmit.disabled = true;
  askStop.hidden = false;
  askController = new AbortController();
  askResult.className = 'ask-result loading';
  askResult.textContent = tr('ask.reading');
  setTranslatedAskStatus('ask.waiting');
  try {{
    const response = await fetch('/api/ask', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json', Accept: 'application/json'}},
      signal: askController.signal,
      body: JSON.stringify({{
        ticker,
        provider: askModel.value,
        language: askLanguage.value,
        depth: 'beginner',
        scope: askScope.value || 'core',
        question,
      }}),
    }});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.message || tr('ask.answer_failed'));
    renderAskAnswer(payload);
    setAskStatus(`${{payload.meta.model}} · ${{payload.meta.latency_ms}} ms · validator passed`, 'ready');
  }} catch (error) {{
    // A stop is the visitor getting what they asked for, not a failure, so it
    // does not get the error colour or the withheld-answer wording.
    const stopped = error.name === 'AbortError';
    askResult.className = stopped ? 'ask-result' : 'ask-result error';
    askResult.textContent = stopped
      ? tr('ask.stopped')
      : (error.message || tr('ask.selected_unavailable'));
    setTranslatedAskStatus(stopped ? 'ask.stopped_status' : 'ask.withheld', {{}},
                           stopped ? 'notice' : 'error');
  }} finally {{
    askController = null;
    askStop.hidden = true;
    askSubmit.disabled = askModel.disabled;
  }}
}});

function renderAskAnswer(payload) {{
  askResult.replaceChildren();
  askResult.className = 'ask-result answered';
  const heading = document.createElement('div');
  heading.className = 'ask-answer-heading';
  const label = document.createElement('span');
  label.dataset.i18n = 'ask.validated_answer';
  label.textContent = tr('ask.validated_answer');
  const model = document.createElement('small');
  model.className = 'ask-answer-meta';
  model.dataset.provider = payload.meta.provider;
  model.dataset.evidenceAsOf = payload.meta.evidence_as_of;
  // Two different times, and conflating them is what made the heading
  // misleading: the evidence date says how current the filings and prices are,
  // and says nothing about when this answer was produced. The server stamps its
  // own; a page served by an older build of the function falls back to the
  // moment the response arrived, which differs from it by one network hop.
  model.dataset.answeredAt = payload.meta.answered_at || new Date().toISOString();
  model.textContent = askAnswerMetaText(model);
  heading.append(label, model);
  askResult.append(heading);
  payload.answer.forEach(claim => askResult.append(renderAskClaim(claim)));
  const details = document.createElement('details');
  details.className = 'ask-limitations';
  const summary = document.createElement('summary');
  summary.dataset.i18n = 'ask.limitations';
  summary.textContent = tr('ask.limitations');
  details.append(summary);
  payload.boundaries.forEach(claim => details.append(renderAskClaim(claim)));
  askResult.append(details);
  const languageNote = document.createElement('p');
  languageNote.className = 'ask-scope-note';
  languageNote.dataset.i18n = 'ask.original_language';
  languageNote.textContent = tr('ask.original_language');
  askResult.append(languageNote);
}}

function formatAskTime(iso) {{
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return iso;
  // The viewer's own clock and locale. The answer was produced at one instant;
  // which wall clock that lands on is the reader's business, not the server's.
  return when.toLocaleString(uiLanguage === 'zh' ? 'zh-CN' : 'en-GB', {{
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  }});
}}

function askAnswerMetaText(element) {{
  return [
    element.dataset.provider,
    tr('ask.answered_at', {{time: formatAskTime(element.dataset.answeredAt)}}),
    tr('ask.evidence_through', {{date: element.dataset.evidenceAsOf}}),
  ].filter(Boolean).join(' · ');
}}

// Rebuilt on the language toggle rather than left in whichever language the
// answer happened to arrive in -- it is built in script, so nothing in
// applyLanguage's `[data-i18n]` sweep would otherwise reach it.
function refreshAskAnswerMeta() {{
  const meta = askResult.querySelector('.ask-answer-meta');
  if (meta) meta.textContent = askAnswerMetaText(meta);
}}

function renderAskClaim(claim) {{
  const article = document.createElement('article');
  const copy = document.createElement('p');
  copy.textContent = claim.text;
  article.append(copy);
  if (claim.citations.length) {{
    const links = document.createElement('div');
    links.className = 'ask-citations';
    claim.citations.forEach(citation => {{
      const link = document.createElement('a');
      link.href = safeAskHref(citation.url);
      link.dataset.citationLabel = citation.label;
      link.textContent = localizedCitationLabel(citation.label);
      if (link.href.startsWith('http')) {{
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
      }}
      links.append(link);
    }});
    article.append(links);
  }}
  return article;
}}


function localizedCitationLabel(label) {{
  if (uiLanguage !== 'zh') return label;
  const labels = {{
    'Latest SEC filing': '最新 SEC 披露',
    'SEC source passage': 'SEC 原文段落',
    'Filing wording comparison': '披露措辞对比',
    'SEC company record': 'SEC 公司记录',
    'Asset Open To Close': '公司开盘至收盘收益',
    'Benchmark Open To Close': '基准开盘至收盘收益',
    'Benchmark Adjusted Move': '扣除基准后的变动',
    'Prior Sample Size': '历史样本数',
    'Historical Magnitude Percentile': '历史反应幅度分位',
    'Asset Total Return': '公司累计回报', 'Asset Annualized Return': '公司年化回报',
    'Asset Max Drawdown': '公司最大回撤', 'Benchmark Total Return': '基准累计回报',
    'Total Return': '累计回报', 'Cagr': '年化复合增长率',
    'Annualized Volatility': '年化波动率', 'Max Drawdown': '最大回撤',
    'Current Drawdown': '当前回撤', 'Worst Day': '最差单日收益',
    'Beta': '贝塔系数', 'Correlation': '相关系数',
    'Ending Value': '期末价值', 'Relative Total Return': '相对累计回报',
    'Observations': '观测数', 'Recovery Sessions': '恢复所需交易日',
    'Max Drawdown Date': '最大回撤日期',
  }};
  const metrics = {{
    'Revenue': '营业收入', 'Gross profit': '毛利润', 'Operating income': '营业利润',
    'Net income': '净利润', 'Operating cash flow': '经营现金流',
    'Capital expenditures': '资本支出', 'Diluted shares': '稀释股本',
    'Total assets': '总资产', "Stockholders' equity": '股东权益',
    'Share-based compensation': '股份薪酬', 'Share repurchases': '股份回购',
    'Dividends paid': '已付股息', 'Free cash flow': '自由现金流',
    'Gross margin': '毛利率', 'Operating margin': '营业利润率',
    'Free cash flow per share': '每股自由现金流',
  }};
  const match = label.match(/^(SEC source for )?(.+?)( FY[0-9]{{4}})?$/);
  if (match && metrics[match[2]]) {{
    return `${{metrics[match[2]]}}${{match[3] || ''}}${{match[1] ? ' · SEC 来源' : ''}}`;
  }}
  return labels[label] || label;
}}

function refreshLocalizedDetails() {{
  document.querySelectorAll('[data-citation-label]').forEach(element => {{
    element.textContent = localizedCitationLabel(element.dataset.citationLabel);
  }});
  document.querySelectorAll('[data-local-date]').forEach(element => {{
    if (!element.dataset.dateEn) element.dataset.dateEn = element.textContent;
    // Use the filed calendar date, without shifting it into the browser timezone.
    const date = element.dataset.localDate.slice(0, 10);
    element.textContent = uiLanguage === 'zh' && /^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$/.test(date)
      ? `${{Number(date.slice(0,4))}}年${{Number(date.slice(5,7))}}月${{Number(date.slice(8,10))}}日${{element.dataset.dateEn.includes(' · ') ? ' · ' + element.dataset.dateEn.split(' · ').slice(1).join(' · ') : ''}}`
      : element.dataset.dateEn;
  }});
  document.querySelectorAll('.item-chip[title]').forEach(element => {{
    const label = element.querySelector('[data-i18n]');
    if (label) element.title = label.textContent;
  }});
  const ariaLabels = {{
    'Company navigation': '公司导航', 'Page storyline': '页面章节',
    'On this page': '本页目录', 'Historical period': '历史期间',
    'Growth of ten thousand dollars compared with benchmark': '一万美元投资价值与基准的对比',
    'Guided research questions': '研究问题引导',
    'Recent filing timeline': '近期披露时间线',
    'Observed filing market reaction': '披露后的历史市场反应',
    'Prior comparable filing changes': '与此前同类披露的变化',
  }};
  document.querySelectorAll('[aria-label]').forEach(element => {{
    const original = element.dataset.ariaEn || element.getAttribute('aria-label');
    const chinese = element.dataset.ariaZh || ariaLabels[original];
    if (!chinese) return;
    element.dataset.ariaEn = original;
    element.setAttribute('aria-label', uiLanguage === 'zh' ? chinese : original);
  }});
}}

function safeAskHref(value) {{
  try {{
    const url = new URL(value, window.location.origin);
    if (url.protocol === 'https:' || (url.protocol === 'http:' && url.origin === window.location.origin)) {{
      return url.href;
    }}
  }} catch (error) {{}}
  return '#ask';
}}


// The self-history scatter. Each point is an earlier filing from this issuer:
// how unusual its language was, against how large its reaction turned out to be.
// Drawn from data already on the page rather than fetched, so it works offline
// and cannot disagree with the card above it.
(function () {{
  const holder = document.getElementById('signal-points');
  const plot = document.getElementById('signal-plot');
  if (!holder || !plot) return;
  let points = [];
  try {{ points = JSON.parse(holder.textContent) || []; }} catch (error) {{ return; }}
  if (!points.length) return;

  const W = 320, H = 210, L = 34, R = 12, T = 14, B = 30;
  const reactions = points.map(p => p.reaction);
  // Clip the vertical scale at the 95th percentile: one twelve-sigma filing in
  // an issuer's history would otherwise flatten every other point onto the axis.
  const sorted = [...reactions].sort((a, b) => a - b);
  const top = sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))];
  const yMax = Math.max(top, 1) * 1.1;
  const x = v => L + v * (W - L - R);
  const y = v => H - B - Math.min(v / yMax, 1) * (H - T - B);

  const parts = [
    `<line x1="${{L}}" y1="${{H - B}}" x2="${{W - R}}" y2="${{H - B}}" class="ax"/>`,
    `<line x1="${{L}}" y1="${{T}}" x2="${{L}}" y2="${{H - B}}" class="ax"/>`,
  ];
  // The materiality line, so a reader can see which points cleared the bar.
  const bar = y(2.0);
  if (bar > T && bar < H - B) {{
    parts.push(`<line x1="${{L}}" y1="${{bar}}" x2="${{W - R}}" y2="${{bar}}" class="bar"/>`);
    parts.push(`<text x="${{W - R}}" y="${{bar - 4}}" class="barlab">2σ</text>`);
  }}
  for (const p of points) {{
    const cls = p.current ? 'pt now' : 'pt';
    const r = p.current ? 5.5 : 3.2;
    parts.push(
      `<circle cx="${{x(p.novelty).toFixed(1)}}" cy="${{y(p.reaction).toFixed(1)}}" ` +
      `r="${{r}}" class="${{cls}}"><title>${{p.date}} · ${{p.items}} · ` +
      `${{p.reaction.toFixed(1)}}σ</title></circle>`);
  }}
  plot.innerHTML = parts.join('');
}})();

const pageNavLinks = Array.from(
  document.querySelectorAll('.page-nav a[href^="#"], .section-nav a[href^="#"]'),
);
const pageSections = pageNavLinks
  .map(link => document.getElementById(link.getAttribute('href').slice(1)))
  .filter(Boolean);

function setActivePageNav(id) {{
  pageNavLinks.forEach(link => {{
    const active = link.getAttribute('href') === `#${{id}}`;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'location');
    else link.removeAttribute('aria-current');
  }});
}}

if ('IntersectionObserver' in window && pageSections.length) {{
  const visible = new Map();
  const observer = new IntersectionObserver(entries => {{
    entries.forEach(entry => visible.set(entry.target.id, entry.isIntersecting));
    const current = pageSections.find(section => visible.get(section.id));
    if (current) setActivePageNav(current.id);
  }}, {{rootMargin: '-150px 0px -55% 0px', threshold: [0.12, 0.35]}});
  pageSections.forEach(section => observer.observe(section));
}}
if (window.location.hash) setActivePageNav(window.location.hash.slice(1));

document.getElementById('language-toggle').addEventListener('click', () => {{
  applyLanguage(uiLanguage === 'en' ? 'zh' : 'en');
}});

applyLanguage(storedLanguage() === 'zh' ? 'zh' : 'en', false);
loadAskModels();
"""


def _index_script() -> str:
    return """
const companies = JSON.parse(document.getElementById('company-data').textContent);
const form = document.getElementById('company-search');
const input = document.getElementById('ticker-search');
const status = document.getElementById('search-status');
const directoryGrid = document.getElementById('directory-grid');
const directoryStatus = document.getElementById('directory-status');
const directoryPrevious = document.getElementById('directory-previous');
const directoryNext = document.getElementById('directory-next');
const directoryCompanies = [...companies].sort((left, right) => left.ticker.localeCompare(right.ticker));
const directoryPageSize = 9;
let directoryPage = 0;
const normalize = value => value.trim().toUpperCase().replace(/[^A-Z0-9]/g, '');
const indexTranslations = {
  en: {
    'nav.earnings': 'Financial results',
    'nav.what': 'What this is',
    'method.overview': 'What this project is',
    'method.overview_copy': ('The problem, the result, and the mistake that made it look twice as good \u2014 in plain words'),
    'nav.research': 'How this is audited',
    'nav.scope': '{count}-company evidence universe',
    'hero.eyebrow': 'SOURCE-BACKED COMPANY INTELLIGENCE',
    'hero.title': 'Understand the company.',
    'hero.emphasis': 'Keep the evidence.',
    'hero.lede': 'Filed financial results and year-over-year changes, historical return and risk, and source-backed questions. Coverage varies by company.',
    'search.label': 'Search {count} locally available companies',
    'search.placeholder': 'Try AAPL or Apple',
    'search.submit': 'Open lens',
    'search.hint': 'Type an exact ticker or company name from the current local universe.',
    'search.scope': '{count} companies are available from the current local evidence set.',
    'search.multiple': 'More than one local company matched. Enter the exact ticker.',
    'search.missing': 'Not in the current local {count}-company universe.',
    'featured': 'Featured examples',
    'card.open': 'Open company lens →',
    'directory.eyebrow': 'LOCAL DIRECTORY',
    'directory.title': 'Explore the company directory',
    'directory.expand': 'Browse all companies',
    'directory.previous': 'Previous',
    'directory.next': 'Next',
    'directory.page': 'Page {page} of {pages} · {count} cached companies',
    'method.eyebrow': 'HOW TO READ A LENS',
    'method.title': 'Company first. Evidence second.',
    'method.expand': 'Under the hood',
    'method.intro': 'Every page follows one order: historical picture, latest SEC disclosure, then company-specific context. Broad market headlines and implementation details stay off the company page so they cannot be mistaken for company evidence.',
    'method.history': 'History',
    'method.history_copy': 'Return and risk against the S&P 500 ETF (SPY)',
    'method.disclosure': 'Disclosure',
    'method.disclosure_copy': 'What the latest 8-K actually says',
    'method.boundary': 'Boundary',
    'method.boundary_copy': 'Citations, limitations, no forecast',
    'method.research': 'Behind the filing research',
    'method.research_copy': 'Evaluation methods, uncertainty, and limitations',
    'method.tech': 'Under the hood: point-in-time SEC ingestion, return and risk calculations, deterministic NLP change filtering, and an optional source-bounded LLM explanation layer.',
    'footer': 'Cached real-data demonstration · SEC EDGAR + vendor-adjusted daily prices',
  },
  zh: {
    'nav.what': '项目介绍',
    'method.overview': '这个项目做什么',
    'method.overview_copy': '研究问题、实测结果，以及如何避免回看历史时高估模型表现',
    'nav.earnings': '财报变化',
    'nav.research': '审计方法',
    'nav.scope': '覆盖 {count} 家公司的证据范围',
    'hero.eyebrow': '基于来源的公司研究',
    'hero.title': '理解一家公司。',
    'hero.emphasis': '保留每条证据。',
    'hero.lede': '查看已披露财报及同比变化、历史收益与风险，再带着问题核对原始资料。数据覆盖因公司而异。',
    'search.label': '搜索本地已有的 {count} 家公司',
    'search.placeholder': '输入 AAPL 或 Apple',
    'search.submit': '打开公司页',
    'search.hint': '请输入当前本地范围内的准确股票代码或公司名称。',
    'search.scope': '当前本地证据集包含 {count} 家公司。',
    'search.multiple': '匹配到多家公司，请输入准确股票代码。',
    'search.missing': '不在当前本地 {count} 家公司的范围内。',
    'featured': '示例公司',
    'card.open': '打开 Company Lens →',
    'directory.eyebrow': '本地公司目录',
    'directory.title': '浏览全部公司',
    'directory.expand': '展开公司目录',
    'directory.previous': '上一页',
    'directory.next': '下一页',
    'directory.page': '第 {page} / {pages} 页 · 共 {count} 家缓存公司',
    'method.eyebrow': '如何阅读公司页',
    'method.title': '先看公司，再核验证据。',
    'method.expand': '技术细节',
    'method.intro': '每个公司页按同一顺序呈现：长期历史表现、最新 SEC 披露、公司相关信息。宽泛市场新闻和实现细节不会混入公司证据。',
    'method.history': '历史表现',
    'method.history_copy': '与标普 500 ETF（SPY）比较收益和风险',
    'method.disclosure': '公司披露',
    'method.disclosure_copy': '最新 8-K 实际说了什么',
    'method.boundary': '证据边界',
    'method.boundary_copy': '引用、局限与不预测原则',
    'method.research': '公告研究的方法与局限',
    'method.research_copy': '展开查看评估方法、不确定性和研究边界',
    'method.tech': '技术基础：时点正确的 SEC 数据摄取、回报与风险计算、确定性 NLP 变化过滤，以及可选的来源受限 LLM 解释层。',
    'footer': '真实缓存数据演示 · SEC EDGAR + 供应商复权日线价格',
  },
};
let indexLanguage = 'en';
const indexTr = (key, values={}) => Object.entries(values).reduce(
  (copy, [name, value]) => copy.replaceAll(`{${name}}`, String(value)),
  indexTranslations[indexLanguage][key] || indexTranslations.en[key] || key,
);

function setSearchStatus(key, values={}, error=false) {
  status.dataset.statusKey = key;
  status.dataset.statusValues = JSON.stringify(values);
  status.classList.toggle('error', error);
  refreshSearchStatus();
}

function refreshSearchStatus() {
  let values = {};
  try { values = JSON.parse(status.dataset.statusValues || '{}'); } catch (error) {}
  status.textContent = indexTr(
    status.dataset.statusKey || 'search.scope',
    {count: companies.length, ...values},
  );
}

function renderDirectory() {
  const pages = Math.max(1, Math.ceil(directoryCompanies.length / directoryPageSize));
  directoryPage = Math.min(Math.max(directoryPage, 0), pages - 1);
  const start = directoryPage * directoryPageSize;
  directoryGrid.replaceChildren();
  directoryCompanies.slice(start, start + directoryPageSize).forEach(company => {
    const link = document.createElement('a');
    link.className = 'directory-link';
    link.href = `${encodeURIComponent(company.ticker.toLowerCase())}.html`;
    const tickerLabel = document.createElement('strong');
    tickerLabel.textContent = company.ticker;
    const name = document.createElement('span');
    name.textContent = company.name;
    const action = document.createElement('small');
    action.textContent = indexTr('card.open');
    link.append(tickerLabel, name, action);
    directoryGrid.append(link);
  });
  directoryStatus.textContent = indexTr('directory.page', {
    page: directoryPage + 1,
    pages,
    count: directoryCompanies.length,
  });
  directoryPrevious.disabled = directoryPage === 0;
  directoryNext.disabled = directoryPage >= pages - 1;
}

function applyIndexLanguage(language, persist=true) {
  indexLanguage = language === 'zh' ? 'zh' : 'en';
  document.documentElement.lang = indexLanguage === 'zh' ? 'zh-CN' : 'en';
  document.querySelectorAll('[data-index-i18n]').forEach(element => {
    element.textContent = indexTr(element.dataset.indexI18n, {count: companies.length});
  });
  document.querySelectorAll('[data-index-i18n-placeholder]').forEach(element => {
    element.placeholder = indexTr(element.dataset.indexI18nPlaceholder, {count: companies.length});
  });
  const toggle = document.getElementById('index-language-toggle');
  toggle.textContent = indexLanguage === 'zh' ? 'EN' : '中文';
  toggle.setAttribute('aria-label', indexLanguage === 'zh' ? 'Switch to English' : '切换为中文');
  toggle.setAttribute('aria-pressed', String(indexLanguage === 'zh'));
  refreshSearchStatus();
  renderDirectory();
  if (persist) {
    try { localStorage.setItem('company-lens-language', indexLanguage); } catch (error) {}
  }
}

form.addEventListener('submit', event => {
  event.preventDefault();
  const query = normalize(input.value);
  const exactTicker = companies.find(company => normalize(company.ticker) === query);
  const exactName = companies.find(company => normalize(company.name) === query);
  const partialMatches = companies.filter(company => normalize(company.name).includes(query));
  const match = exactTicker || exactName || (partialMatches.length === 1 ? partialMatches[0] : null);
  if (match) {
    window.location.href = `${match.ticker.toLowerCase()}.html`;
    return;
  }
  setSearchStatus(
    partialMatches.length ? 'search.multiple' : 'search.missing',
    {count: companies.length},
    true,
  );
});

input.addEventListener('input', () => {
  setSearchStatus('search.scope', {count: companies.length});
});

directoryPrevious.addEventListener('click', () => {
  directoryPage -= 1;
  renderDirectory();
});
directoryNext.addEventListener('click', () => {
  directoryPage += 1;
  renderDirectory();
});

document.getElementById('index-language-toggle').addEventListener('click', () => {
  applyIndexLanguage(indexLanguage === 'en' ? 'zh' : 'en');
});
let savedIndexLanguage = null;
try { savedIndexLanguage = localStorage.getItem('company-lens-language'); } catch (error) {}
applyIndexLanguage(savedIndexLanguage === 'zh' ? 'zh' : 'en', false);
"""


def _css() -> str:
    return """
:root{--paper:#f5f4ec;--panel:#fff;--ink:#183c35;--muted:#657567;--line:#d8ddd3;--blue:#426b50;--blue-soft:#e9efdf;--green:#14765d;--green-soft:#eaf6f0;--amber:#a96418;--amber-soft:#fff5e8;--navy:#183c35;--shadow:0 18px 50px rgba(24,42,53,.08)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:16px;line-height:1.55}.topbar{height:70px;padding:0 max(28px,calc((100vw - 1240px)/2));display:flex;align-items:center;border-bottom:1px solid var(--line);background:rgba(245,244,236,.94);position:sticky;top:0;z-index:20;backdrop-filter:blur(16px)}.brand{display:flex;align-items:center;gap:10px;color:var(--navy);font-weight:760;text-decoration:none;letter-spacing:-.02em}.brand-mark{display:grid;place-items:center;width:32px;height:32px;border-radius:9px;background:var(--navy);color:white;font-size:11px;letter-spacing:.04em}.topbar nav{display:flex;align-items:center;margin-left:55px;gap:8px}.company-search-link{padding:7px 10px;border-radius:8px;color:var(--muted);font-size:12px;font-weight:700;text-decoration:none}.company-search-link:hover{background:var(--panel);color:var(--ink)}.current-symbol{padding:5px 8px;border:1px solid var(--line);border-radius:7px;background:var(--panel);color:var(--ink);font-size:11px;font-weight:800;letter-spacing:.06em}.site-link{padding:7px 9px;border-radius:7px;color:var(--muted);font-size:11px;font-weight:750;text-decoration:none;white-space:nowrap}.site-link:hover{background:var(--panel);color:var(--blue)}.trust-label{margin-left:auto;color:var(--green);font-size:12px;font-weight:750;text-transform:uppercase;letter-spacing:.08em}.language-toggle{margin-left:14px;padding:6px 10px;border:1px solid var(--line);border-radius:999px;background:var(--panel);color:var(--ink);font:750 11px/1.2 "Avenir Next","Segoe UI",sans-serif;cursor:pointer}.language-toggle:hover{border-color:#aebbc0;color:var(--blue)}.language-toggle:focus-visible{outline:3px solid rgba(66,107,80,.18);outline-offset:2px}main{max-width:1240px;margin:auto;padding:30px 28px 90px}.company-hero{display:flex;justify-content:space-between;align-items:end;padding:65px 0 48px}.eyebrow{margin:0 0 10px;color:var(--blue);font-size:11px;font-weight:800;letter-spacing:.13em}.company-title{display:flex;align-items:center;gap:16px}.company-title h1{margin:0;font-family:Georgia,"Times New Roman",serif;font-size:clamp(40px,5vw,68px);font-weight:500;line-height:1.05;letter-spacing:-.045em}.company-title>span{padding:7px 10px;background:var(--navy);border-radius:8px;color:#fff;font-size:13px;font-weight:800;letter-spacing:.06em}.hero-copy{max-width:650px;margin:17px 0 0;color:var(--muted);font-size:18px}.market-observation{min-width:220px;padding-left:25px;border-left:1px solid var(--line);display:flex;flex-direction:column;align-items:flex-end}.market-observation span,.ending-card>span{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em;font-weight:700}.market-observation strong{font-family:Georgia,serif;font-size:38px;font-weight:500}.market-observation small{color:var(--muted)}section{margin-bottom:28px;padding:38px;border:1px solid var(--line);border-radius:20px;background:var(--panel);box-shadow:0 1px 0 rgba(255,255,255,.6)}.section-heading{display:flex;align-items:start;justify-content:space-between;gap:24px}.section-heading h2,.trust-section h2{margin:0;font-family:Georgia,serif;font-size:34px;font-weight:500;letter-spacing:-.025em}.mode-badge,.freshness{padding:7px 10px;border:1px solid var(--line);border-radius:999px;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em}.brief-section{background:var(--navy);color:#fff;border-color:var(--navy);box-shadow:var(--shadow)}.brief-section .eyebrow{color:#78a7ff}.brief-section .mode-badge{border-color:#476656;color:#aebfca}.brief-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;margin-top:28px;background:#476656;border:1px solid #476656;border-radius:14px;overflow:hidden}.brief-card{min-height:190px;padding:25px;background:#122d41}.brief-card>span{font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.1em}.brief-card.observed>span{color:#80aaff}.brief-card.calculated>span{color:#5fd0aa}.brief-card.interpreted>span{color:#e9b66d}.brief-card p{font-family:Georgia,serif;font-size:20px;line-height:1.45}.claim-links{display:flex;gap:8px}.claim-links a{font-size:11px;color:#daefc6;text-decoration:none;border-bottom:1px solid #6e8290}.authority-row{display:flex;gap:25px;margin-top:22px;color:#aebfca;font-size:11px}.authority-row span{display:flex;align-items:center;gap:7px}.dot{width:7px;height:7px;border-radius:50%}.dot.observed{background:#80aaff}.dot.calculated{background:#5fd0aa}.dot.interpreted{background:#e9b66d}.performance-section{padding-bottom:30px}.performance-heading{align-items:center}.period-control{display:flex;padding:4px;background:var(--paper);border-radius:10px}.period-button{border:0;background:transparent;padding:7px 13px;border-radius:7px;color:var(--muted);font-weight:750;cursor:pointer}.period-button:hover{color:var(--ink)}.period-button.active{background:var(--panel);color:var(--blue);box-shadow:0 2px 8px rgba(20,40,55,.08)}.history-controls{display:flex;flex-wrap:wrap;gap:10px;justify-content:flex-end}.benchmark-control{display:flex;padding:4px;background:var(--paper);border-radius:10px}.benchmark-button{border:0;background:transparent;padding:7px 13px;border-radius:7px;color:var(--muted);font-weight:750;cursor:pointer}.benchmark-button:hover{color:var(--ink)}.benchmark-button.active{background:var(--panel);color:var(--blue);box-shadow:0 2px 8px rgba(20,40,55,.08)}.benchmark-button:disabled,.period-button:disabled{opacity:.4;cursor:not-allowed}.benchmark-note{max-width:730px;margin:-18px 0 22px;color:var(--muted);font-size:12px}.benchmark-note:empty{display:none}.section-intro{max-width:730px;margin:10px 0 28px;color:var(--muted)}.performance-layout{display:grid;grid-template-columns:minmax(0,1fr) 230px;gap:18px}.chart-panel{position:relative;border:1px solid var(--line);border-radius:14px;padding:18px;background:#fbfcfc}.chart-legend{height:25px;display:flex;align-items:center;gap:18px;color:var(--muted);font-size:11px}.chart-legend>span:last-child{margin-left:auto}.line{display:inline-block;width:18px;height:3px;border-radius:2px;margin-right:6px;vertical-align:middle}.line.asset{background:var(--blue)}.line.benchmark{background:#8a969e}#growth-chart{display:block;width:100%;overflow:visible}#growth-chart path{fill:none;stroke-linecap:round;stroke-linejoin:round}#asset-path{stroke:var(--blue);stroke-width:3}#benchmark-path{stroke:#99a4ab;stroke-width:2}#chart-grid line{stroke:#e6eaeb;stroke-width:1}#chart-labels text{font-size:10px;fill:#7c888f}#hover-line{stroke:#91a0a8;stroke-dasharray:3 3;opacity:0;pointer-events:none}#asset-point{fill:var(--blue);stroke:white;stroke-width:2;opacity:0}#benchmark-point{fill:#89969e;stroke:white;stroke-width:2;opacity:0}.chart-hit{fill:transparent;cursor:crosshair}.chart-tooltip{position:absolute;top:72px;transform:translateX(-50%);display:none;min-width:155px;padding:10px 12px;background:var(--navy);color:#fff;border-radius:9px;box-shadow:var(--shadow);pointer-events:none;font-size:11px}.chart-tooltip.visible{display:flex;flex-direction:column}.chart-tooltip b{margin-bottom:4px}.ending-card{padding:24px;background:var(--blue-soft);border-radius:14px;display:flex;flex-direction:column}.ending-card>strong{margin:8px 0 2px;font-family:Georgia,serif;font-size:34px;font-weight:500;color:#173f91}.ending-card>small{color:#4d6d9f}.mini-comparison{margin-top:auto;padding-top:18px;border-top:1px solid #cfdbf3;display:flex;flex-direction:column;color:#4d6d9f;font-size:11px}.mini-comparison b{font-size:17px;color:#173f91}.metric-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-top:18px}.metric-card{padding:16px;border:1px solid var(--line);border-radius:12px}.metric-card>span{display:flex;justify-content:space-between;min-height:36px;color:var(--muted);font-size:11px;font-weight:700}.metric-card i{display:grid;place-items:center;width:17px;height:17px;border:1px solid var(--line);border-radius:50%;font-style:normal}.metric-card strong{display:block;font-family:Georgia,serif;font-size:25px;font-weight:500}.metric-card small{display:none}.risk-note{display:flex;gap:20px;margin-top:18px;padding:15px 18px;border-left:3px solid var(--amber);background:var(--amber-soft);color:#664b2e;font-size:13px}.risk-note strong{min-width:130px}.filing-list{display:flex;flex-direction:column;gap:10px}.filing-card{border:1px solid var(--line);border-radius:14px;overflow:hidden}.filing-card summary{list-style:none;padding:18px 20px;display:flex;align-items:center;justify-content:space-between;cursor:pointer}.filing-card summary::-webkit-details-marker{display:none}.filing-card summary>div:first-child{display:grid;grid-template-columns:auto 1fr;gap:2px 11px;align-items:center}.filing-card summary strong{font-size:15px}.filing-card summary small{grid-column:2;color:var(--muted)}.filing-form{grid-row:1/3;padding:7px 9px;background:var(--green-soft);color:var(--green);border-radius:8px;font-weight:800}.filing-summary-meta{display:flex;align-items:center;gap:18px;color:var(--muted);font-size:12px}.filing-summary-meta i{font-size:18px;transition:transform .2s}.filing-card[open] .filing-summary-meta i{transform:rotate(180deg)}.filing-body{padding:0 20px 22px;border-top:1px solid var(--line);background:#fbfcfc}.filing-items{display:flex;flex-wrap:wrap;gap:7px;padding:16px 0}.item-chip,.number-chip{padding:5px 8px;border-radius:7px;background:var(--paper);color:var(--muted);font-size:11px;text-decoration:none}.number-chip{background:var(--blue-soft);color:#2855a7;font-weight:750}.filing-columns{display:grid;grid-template-columns:minmax(0,1fr) 230px;gap:30px}.filing-columns h3{margin:16px 0 8px;font-size:11px;text-transform:uppercase;letter-spacing:.08em}.number-list{display:flex;flex-wrap:wrap;gap:6px}.passages{display:flex;flex-direction:column;gap:8px}blockquote{margin:0;padding:14px 16px;border-left:2px solid #9db8ed;background:#fff}blockquote p{margin:0 0 7px;font-family:Georgia,serif;font-size:15px}blockquote a,.filing-columns aside a{color:var(--blue);font-size:10px;text-decoration:none}.filing-columns aside{padding:16px;border-radius:10px;background:var(--paper);display:flex;flex-direction:column;align-items:start;gap:8px;font-size:11px;color:var(--muted)}.filing-columns aside>span{text-transform:uppercase;letter-spacing:.08em}.filing-columns aside code{word-break:break-all;color:var(--ink)}.missing,.empty{color:var(--muted);font-size:12px;font-style:italic}.trust-section{background:#e9ece9}.trust-section>.eyebrow{color:var(--green)}.trust-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:15px;margin-top:28px}.trust-grid article{padding:20px;background:rgba(255,255,255,.6);border-radius:12px}.trust-grid article>span{font-family:Georgia,serif;color:var(--green);font-size:24px}.trust-grid h3{margin:8px 0 4px}.trust-grid p{margin:0;color:var(--muted);font-size:13px}footer{max-width:1240px;margin:auto;padding:28px;display:flex;justify-content:space-between;border-top:1px solid var(--line);color:var(--muted);font-size:12px}footer>div:first-child{display:flex;flex-direction:column}.footer-meta{display:flex;gap:20px}
.freshness-group{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px}.entity-chip{display:inline-flex;align-items:center;gap:6px}.entity-chip small{padding-right:6px;border-right:1px solid #b9c9e8;color:#60749a;font-size:8px;text-transform:uppercase;letter-spacing:.05em}.entity-mark{padding:1px 3px;border-radius:3px;background:#e8efff;color:inherit}.entity-mark.percentage{background:#e7f5ee}.entity-mark.date{background:#fff0da}.reaction-panel{margin:0 0 14px;padding:18px;border:1px solid #cfe0d8;border-radius:12px;background:#f3f8f5}.reaction-heading{display:flex;justify-content:space-between;gap:20px}.reaction-heading>div{display:flex;flex-direction:column}.reaction-heading span{color:var(--green);font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.07em}.reaction-heading strong{font-size:13px}.reaction-heading>small{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.07em}.reaction-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:13px}.reaction-grid>div{padding:12px;border:1px solid #dbe8e1;border-radius:9px;background:#fff;display:flex;flex-direction:column}.reaction-grid span{color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.07em}.reaction-grid strong{margin:3px 0;font-family:Georgia,serif;font-size:19px;font-weight:500}.reaction-grid small,.reaction-panel>p{color:var(--muted);font-size:10px}.reaction-panel>p{margin:12px 0 0}.reaction-empty{display:flex;flex-direction:column;margin:0 0 14px;padding:13px 15px;border:1px dashed #cfe0d8;border-radius:10px;color:var(--muted);font-size:11px}.reaction-empty strong{color:var(--ink)}.comparison-panel{margin:0 0 22px;padding:18px;border:1px solid #cddbed;border-radius:12px;background:#f5f8fd}.comparison-heading{display:flex;justify-content:space-between;gap:20px}.comparison-heading>div{display:flex;flex-direction:column}.comparison-heading span{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.07em}.comparison-heading strong{font-size:13px}.comparison-heading a,.change-quote a{color:var(--blue);font-size:10px;text-decoration:none}.change-counts{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}.change-count{padding:4px 7px;border-radius:999px;font-size:10px;font-weight:750}.change-count.changed{background:#fff1d8;color:#825616}.change-count.added{background:var(--green-soft);color:var(--green)}.change-count.removed{background:#f8e9e7;color:#98473e}.change-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:12px}.change-card{padding:12px;border:1px solid var(--line);border-radius:9px;background:#fff}.change-card header{display:flex;justify-content:space-between;gap:10px}.change-card header>strong{font-size:11px;text-transform:uppercase;letter-spacing:.07em}.similarity{color:var(--muted);font-size:10px}.change-quote{margin-top:9px;padding-left:9px;border-left:2px solid #b9c8df}.change-quote>span{color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.08em}.change-quote p{margin:2px 0 5px;font-family:Georgia,serif;font-size:13px;line-height:1.4}.comparison-empty{display:flex;flex-direction:column;margin:0 0 22px;padding:13px 15px;border:1px dashed var(--line);border-radius:10px;color:var(--muted);font-size:11px}.comparison-empty strong{color:var(--ink)}.profile-category{margin:18px 0 0;color:var(--blue);font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.09em}.hero-copy{margin-top:6px}.profile-meta{display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:14px;color:var(--muted);font-size:11px}.profile-meta a{color:var(--blue);text-decoration:none;border-bottom:1px solid #aac0eb}.metric-grid{grid-template-columns:repeat(4,1fr)}
.timeline-panel{margin:0 0 20px;padding:18px;border:1px solid var(--line);border-radius:12px;background:#fbfcfc}.timeline-heading{display:flex;justify-content:space-between;gap:20px}.timeline-heading>div{display:flex;flex-direction:column}.timeline-heading span{color:var(--blue);font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.07em}.timeline-heading strong{font-size:13px}.timeline-heading>small{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.06em}.timeline-track{position:relative;display:grid;grid-auto-flow:column;grid-auto-columns:minmax(155px,1fr);gap:8px;margin-top:16px;padding-top:14px;overflow-x:auto;scrollbar-width:thin}.timeline-track:before{content:"";position:absolute;top:20px;left:12px;right:12px;height:1px;background:var(--line)}.timeline-event{position:relative;min-height:145px;padding:20px 12px 12px;border:1px solid var(--line);border-radius:9px;background:#fff;color:var(--ink);text-decoration:none;display:flex;flex-direction:column}.timeline-event>i{position:absolute;top:-10px;left:14px;width:13px;height:13px;border:3px solid #fff;border-radius:50%;background:#8d989f;box-shadow:0 0 0 1px var(--line)}.timeline-event.positive>i{background:var(--green)}.timeline-event.negative>i{background:#a74e43}.timeline-event>span,.timeline-event>small{color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.05em}.timeline-event>strong{margin:5px 0 2px;font-size:11px;line-height:1.35}.timeline-event>b{margin-top:auto;font-size:12px}.timeline-event>em{color:var(--muted);font-size:9px;font-style:normal}.timeline-panel>p{margin:11px 0 0;color:var(--muted);font-size:10px}
.topbar .section-nav{margin-left:auto;gap:3px}.section-nav a{padding:7px 9px;border-radius:7px;color:var(--muted);font-size:11px;font-weight:750;text-decoration:none}.section-nav a:hover{background:var(--panel);color:var(--blue)}.trust-label{margin-left:22px}.company-hero{padding:46px 0 34px}.evidence-flow{display:flex;align-items:center;gap:9px;margin-top:18px;color:var(--muted);font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.07em}.evidence-flow span{padding:5px 8px;border:1px solid var(--line);border-radius:999px;background:rgba(255,255,255,.62)}.evidence-flow i{color:var(--blue);font-style:normal}.brief-section{background:linear-gradient(135deg,#0d2436 0%,#132f43 100%)}.brief-intro{max-width:680px;margin:9px 0 0;color:#aebfca;font-size:13px}.brief-grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:10px;margin-top:26px;background:transparent;border:0;border-radius:0;overflow:visible}.brief-card{min-height:0;padding:24px;border:1px solid #476656;border-radius:13px;background:rgba(16,43,62,.82)}.brief-lead{grid-column:span 7;background:linear-gradient(145deg,#173a55,#122d41)}.brief-numbers{grid-column:span 5;background:#102f38}.brief-reading,.brief-limit{grid-column:span 6}.brief-limit{background:#302c2a;border-color:#5b4a3b}.brief-card>span,.brief-card-heading>span{font-size:10px;font-weight:850;text-transform:uppercase;letter-spacing:.11em}.brief-card.observed>span,.brief-card.observed .brief-card-heading>span{color:#80aaff}.brief-card.calculated>span{color:#5fd0aa}.brief-card.interpreted>span{color:#b7c9ff}.brief-card.guardrail>span{color:#e9b66d}.brief-card-heading{display:flex;justify-content:space-between;gap:18px}.brief-lead a,.brief-numbers a{color:#daefc6;font-size:10px;text-decoration:none;border-bottom:1px solid #6e8290}.filing-lead-header{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:12px 16px;align-items:center;padding:18px 20px;border-bottom:1px solid var(--line)}.filing-lead-header .eyebrow{margin:0 0 4px}.filing-lead-header h3{margin:0;font-size:18px;line-height:1.25}.filing-lead-header small{color:var(--muted)}.filing-lead-header a{color:var(--blue);font-size:11px;font-weight:750;text-decoration:none}.filing-lead .filing-body{border-top:0}.brief-card h3{max-width:540px;margin:18px 0 7px;font-family:Georgia,serif;font-size:26px;font-weight:500;line-height:1.15}.brief-card p{margin:11px 0;font-family:Georgia,serif;font-size:17px;line-height:1.48}.brief-lead>p{font-size:19px}.brief-meta{display:flex;flex-wrap:wrap;gap:6px;margin:18px 0 8px}.brief-meta span{padding:5px 7px;border:1px solid #466177;border-radius:6px;color:#bacad4;font-size:9px}.brief-metrics{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:19px 0 14px}.brief-metrics>div{padding:14px;border:1px solid #28514e;border-radius:10px;background:rgba(9,33,37,.55)}.brief-metrics strong{display:block;font-family:Georgia,serif;font-size:31px;font-weight:500;color:#77ddb8}.brief-metrics small{color:#9bb9ae;font-size:9px;text-transform:uppercase;letter-spacing:.06em}.brief-numbers p{color:#b8c9c4;font-family:inherit;font-size:11px}.claim-links{flex-wrap:wrap}.authority-row{align-items:center}.authority-row span b{color:#fff;font-size:9px}.authority-row>em{color:#627786;font-style:normal}.diagnostic-heading{display:flex;justify-content:space-between;align-items:end;margin-top:22px;padding-top:17px;border-top:1px solid var(--line)}.diagnostic-heading span{font-size:12px;font-weight:800}.diagnostic-heading small{color:var(--muted);font-size:10px}.metric-grid{grid-template-columns:repeat(3,1fr);margin-top:10px}.metric-card{background:#fbfcfc;transition:border-color .18s,transform .18s}.metric-card:hover{border-color:#b9c9d8;transform:translateY(-1px)}.trust-grid article>b{display:block;margin-top:7px;color:var(--green);font-size:8px;letter-spacing:.1em}#brief,#ask,#performance,#filings,#context,#page-nav,#method{scroll-margin-top:150px}.section-nav a:focus-visible,.brief-card a:focus-visible,.headline-card a:focus-visible{outline:3px solid #80aaff;outline-offset:3px}
.page-nav{position:sticky;top:70px;z-index:14;display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:28px;margin:0 0 28px;padding:12px 14px;border:1px solid var(--line);background:rgba(245,244,236,.96);backdrop-filter:blur(14px)}.page-nav p{margin:0}.page-nav>div:first-child{min-width:170px}.page-nav>div:first-child strong{font:500 17px/1.2 Georgia,serif}.page-nav-links{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(108px,1fr);gap:5px;overflow-x:auto}.page-nav-links a{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:8px;padding:10px 11px;border:1px solid transparent;color:var(--muted);text-decoration:none}.page-nav-links a span{color:#97a3aa;font-size:9px;font-weight:800}.page-nav-links a b{font-size:11px}.page-nav-links a:hover{border-color:var(--line);background:var(--panel);color:var(--blue)}.page-nav-links a.active{border-color:var(--navy);background:var(--navy);color:#fff}.page-nav-links a.active span{color:#87afff}.section-nav a.active{background:var(--panel);color:var(--blue)}#page-nav{scroll-margin-top:82px}
.context-section{background:#f9faf8}.context-status{padding:7px 10px;border:1px solid var(--line);border-radius:999px;color:var(--green);font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.07em}.context-status.stale{color:var(--amber);border-color:#e5c89e;background:var(--amber-soft)}.headline-list{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.headline-card{padding:17px;border:1px solid var(--line);border-radius:12px;background:#fff;display:flex;flex-direction:column;align-items:flex-start}.headline-card h3{margin:13px 0 11px;font:500 18px/1.35 Georgia,serif}.headline-meta{display:flex;flex-direction:column;color:var(--muted);font-size:10px}.headline-card>a{margin-top:auto;padding-top:15px;color:var(--blue);font-size:10px;font-weight:750;text-decoration:none}
@media(max-width:900px){.trust-label{display:none}.company-hero{align-items:start}.brief-grid,.trust-grid{grid-template-columns:1fr}.brief-card{min-height:auto}.performance-layout{grid-template-columns:1fr}.ending-card{min-height:190px}.metric-grid{grid-template-columns:repeat(3,1fr)}.filing-columns{grid-template-columns:1fr}.authority-row{flex-wrap:wrap}.section-nav{display:none}.brief-grid{gap:8px}.brief-metrics strong{font-size:28px}.headline-list{grid-template-columns:1fr}}
@media(max-width:620px){.topbar{padding:0 16px}.topbar nav{margin-left:auto}.company-search-link{padding:6px}.trust-label{display:none}.brand>span:last-child{display:none}main{padding:18px 14px 60px}.company-hero{padding:42px 0 30px;flex-direction:column;gap:25px}.market-observation{align-items:start;border-left:0;padding-left:0}.company-title{align-items:start}.company-title h1{font-size:42px}section{padding:24px 18px}.section-heading{flex-direction:column}.performance-heading{align-items:start}.metric-grid{grid-template-columns:repeat(2,1fr)}.period-control{width:100%}.period-button{flex:1}.risk-note{flex-direction:column;gap:4px}.filing-card summary strong{max-width:190px}.filing-summary-meta>span{display:none}.footer-meta{display:none}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{transition:none!important}}
@media(max-width:620px){.profile-meta{flex-direction:column;align-items:flex-start;gap:3px}.timeline-heading,.reaction-heading,.comparison-heading{flex-direction:column;gap:6px}.reaction-grid,.change-list{grid-template-columns:1fr}.timeline-track{grid-auto-columns:minmax(145px,72vw)}.topbar .section-nav,.company-search-link{display:none}.topbar .company-nav .site-link{margin-left:auto;color:var(--muted);font-size:11px;font-weight:700;text-decoration:none;white-space:nowrap}.company-nav .site-link+.site-link{margin-left:16px}.company-nav .site-link:hover{color:var(--blue)}.company-nav{margin-left:auto}.company-hero{padding:24px 0 18px;gap:13px}.hero-copy{font-size:15px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}.profile-meta>span{display:none}.profile-meta{margin-top:8px}.evidence-flow{display:none}.market-observation{width:100%;padding:11px 14px;border:1px solid var(--line);border-radius:12px;background:var(--panel);align-items:flex-start}.market-observation strong{font-size:29px}.brief-card{padding:19px}.brief-card h3{font-size:22px}.brief-card p,.brief-lead>p{font-size:16px}.brief-card-heading{flex-direction:column;gap:5px}.brief-metrics{grid-template-columns:1fr 1fr}.authority-row{gap:8px}.authority-row>em{display:none}.diagnostic-heading{align-items:start;flex-direction:column;gap:2px}.metric-grid{grid-template-columns:1fr 1fr}.metric-card{padding:13px}.trust-grid{gap:8px}}
body{font-family:"Avenir Next","Segoe UI",sans-serif}.company-hero{border:0;border-radius:0;background:transparent;box-shadow:none;margin-bottom:0}.brief-section{border-radius:8px}.brief-grid{grid-template-columns:repeat(12,minmax(0,1fr));gap:0;border-top:1px solid #476656;border-bottom:1px solid #476656}.brief-card{border:0;border-radius:0;background:transparent}.brief-lead{border-right:1px solid #476656}.brief-metrics>div{padding:10px 0;border:0;border-radius:0;background:transparent}.brief-metrics>div+div{padding-left:18px;border-left:1px solid #28514e}.brief-boundary{grid-column:1/-1;margin:0;padding:17px 24px;color:#aebfca;font-size:12px}.brief-boundary strong{color:#e9b66d}.performance-section,.filings-section,.context-section{padding:58px 0;border:0;border-top:1px solid var(--line);border-radius:0;background:transparent;box-shadow:none}.diagnostics-disclosure{margin-top:20px;border-top:1px solid var(--line)}.diagnostics-disclosure>summary,.source-details>summary{padding:14px 0;color:var(--blue);font-size:12px;font-weight:750;cursor:pointer}.metric-card{border-radius:3px;background:rgba(255,255,255,.55)}.filing-card{border-radius:4px;background:#fff}.filing-card summary{min-height:76px}.reaction-panel,.comparison-panel{border-width:0 0 0 3px;border-radius:0}.reaction-grid>div{border:0;border-left:1px solid #dbe8e1;border-radius:0;background:transparent}.reaction-grid>div:first-child{border-left:0}.comparison-clear{display:flex;flex-direction:column;margin-top:14px;color:var(--muted);font-size:12px}.comparison-clear strong{margin-bottom:3px;color:var(--ink)}.source-details{margin-top:8px;border-top:1px solid var(--line)}.filing-columns aside{border-radius:3px}.context-freshness{margin:-14px 0 20px;color:var(--muted);font-size:10px}.headline-list{grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:0;border-top:1px solid var(--line)}.headline-card{padding:20px 22px;border:0;border-right:1px solid var(--line);border-radius:0;background:transparent}.headline-card:last-child{border-right:0}.headline-card h3{margin:10px 0 14px}.headline-meta{display:flex;flex-direction:row;flex-wrap:wrap;gap:5px 12px}.headline-meta span:first-child{color:var(--ink);font-weight:750}.headline-card>a{padding-top:2px}footer a{margin-top:5px;color:var(--blue);text-decoration:none}#brief,#ask,#performance,#filings,#context{scroll-margin-top:150px}
.signal-section{padding:58px 0;border-top:1px solid var(--line)}.signal-badge{padding:8px 14px;border-radius:999px;font-size:11px;font-weight:850;text-transform:uppercase;letter-spacing:.07em;white-space:nowrap}.signal-badge.urgent{background:#fbeceb;color:#a4322a;border:1px solid #e8b6b0}.signal-badge.watch{background:#fdf4e3;color:#8a6412;border:1px solid #e6d3a4}.signal-badge.calm{background:#eef5f0;color:#2f6b4a;border:1px solid #bcd8c7}.signal-badge.muted{background:#f2f3f4;color:var(--muted);border:1px solid var(--line)}.signal-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;margin:26px 0 0;background:var(--line);border:1px solid var(--line)}.signal-stats>div{background:#fff;padding:18px 20px}.signal-stats b{display:block;font:500 30px/1 Georgia,serif}.signal-stats span{display:block;margin-top:7px;color:var(--muted);font-size:11px;line-height:1.5}.signal-grid{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:28px;margin-top:26px;align-items:start}.signal-why h3{margin:0 0 10px;font:500 17px/1.3 Georgia,serif}.signal-why ul{margin:0;padding-left:18px}.signal-why li{margin-bottom:7px;font-size:14px;line-height:1.6}.signal-boundary{margin-top:16px;padding:12px 15px;background:#f6f7f8;border-left:3px solid var(--blue);color:var(--muted);font-size:12.5px;line-height:1.6}.signal-chart{margin:0;padding:14px;border:1px solid var(--line);background:#fff}.signal-chart svg{width:100%;height:auto;display:block}.signal-chart .ax{stroke:#d8ddd3;stroke-width:1}.signal-chart .bar{stroke:#c8b48a;stroke-width:1;stroke-dasharray:3 3}.signal-chart .barlab{fill:#a08a5e;font-size:8px;text-anchor:end}.signal-chart .pt{fill:#9fb2c4}.signal-chart .pt.now{fill:var(--blue);stroke:#fff;stroke-width:1.5}.signal-chart figcaption{display:flex;justify-content:space-between;margin-top:8px;color:var(--muted);font-size:10px}.signal-footer{margin-top:22px;color:var(--muted);font-size:11px}@media(max-width:820px){.signal-grid{grid-template-columns:1fr}}.vol-section{padding:58px 0;border-top:1px solid var(--line)}.vol-bar{margin:26px 0 0}.vol-track{position:relative;height:44px;border:1px solid var(--line);background:#fff}.vol-band{position:absolute;top:0;bottom:0;background:var(--blue-soft);border-left:1px solid #aec2e9;border-right:1px solid #aec2e9}.vol-median{position:absolute;top:0;bottom:0;width:2px;background:var(--blue)}.vol-usual{position:absolute;top:-5px;bottom:-5px;width:1px;background:#a08a5e;border-left:1px dashed #a08a5e}.vol-scale{display:flex;justify-content:space-between;margin-top:6px;color:var(--muted);font-size:10px}@media(max-width:620px){.vol-section{padding:40px 0}}.ask-section{padding:58px 0;border:0;border-top:1px solid var(--line);border-radius:0;background:transparent;box-shadow:none}.ask-validation{padding:7px 10px;border:1px solid #b9d8ca;border-radius:999px;color:var(--green);font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.07em}.ask-layout{display:grid;grid-template-columns:minmax(0,5fr) minmax(320px,4fr);border:1px solid var(--line);background:var(--panel)}.ask-form{padding:28px;border-right:1px solid var(--line)}.ask-controls{display:grid;grid-template-columns:minmax(0,1fr) 128px minmax(0,150px);gap:12px}.ask-form label{display:flex;flex-direction:column;gap:7px;color:var(--muted);font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.08em}.ask-form select,.ask-form textarea{width:100%;border:1px solid var(--line);border-radius:4px;background:#fff;color:var(--ink);font:500 14px/1.5 "Avenir Next","Segoe UI",sans-serif}.ask-form select{height:43px;padding:0 11px}.ask-form textarea{resize:vertical;min-height:90px;padding:12px}.ask-form select:focus,.ask-form textarea:focus{outline:3px solid rgba(66,107,80,.14);border-color:var(--blue)}.ask-question{margin-top:17px}.ask-suggestions{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}.ask-suggestions button{padding:6px 9px;border:1px solid var(--line);border-radius:999px;background:transparent;color:var(--blue);font-size:10px;cursor:pointer}.ask-suggestions button:hover{background:var(--blue-soft)}.ask-submit-row{display:flex;align-items:center;gap:13px;margin-top:20px}.ask-submit-row>button{min-width:120px;padding:11px 16px;border:0;border-radius:4px;background:var(--navy);color:#fff;font-weight:800;cursor:pointer}.ask-submit-row>button:disabled{opacity:.45;cursor:not-allowed}.ask-submit-row>span{color:var(--muted);font-size:10px}.ask-submit-row>span.ready{color:var(--green)}.ask-submit-row>span.error{color:#98473e}.ask-result{min-height:330px;padding:28px;background:#f8faf8;color:var(--muted);font-size:13px}.ask-result-kicker,.ask-answer-heading>span{margin:0;color:var(--green);font-size:10px;font-weight:850;letter-spacing:.1em}.ask-result>ol{margin:18px 0 0;padding:0;list-style:none}.ask-result>ol li{display:grid;grid-template-columns:25px 1fr;gap:10px;padding:12px 0;border-top:1px solid var(--line)}.ask-result>ol li span{color:var(--green);font-weight:850}.ask-result.loading{display:grid;place-items:center}.ask-result.error{display:grid;place-items:center;color:#98473e}.ask-answer-heading{display:flex;justify-content:space-between;gap:15px;padding-bottom:12px;border-bottom:1px solid var(--line)}.ask-answer-heading small{color:var(--muted)}.ask-result article{padding:15px 0;border-bottom:1px solid var(--line)}.ask-result article p{margin:0;color:var(--ink);font:500 17px/1.45 Georgia,serif}.ask-citations{display:flex;flex-wrap:wrap;gap:7px;margin-top:9px}.ask-citations a{color:var(--blue);font-size:10px;text-decoration:none;border-bottom:1px solid #aec2e9}.ask-limitations{margin-top:15px}.ask-limitations>summary{color:var(--amber);font-size:11px;font-weight:800;cursor:pointer}.ask-limitations article p{font:inherit;color:var(--muted)}.ask-boundary{margin:14px 0 0;color:var(--muted);font-size:10px}.ask-boundary strong{color:var(--ink)}
.result-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:18px;margin:24px 0}.result-card{padding:20px;border:1px solid var(--line);border-radius:12px}.result-card h3{font-size:14px}.metric-method{margin-top:12px;font-size:12px}.metric-method>summary{cursor:pointer;color:var(--green)}.metric-method code{overflow-wrap:anywhere}.metric-method ul{padding-left:18px}.result-card>strong{display:block;font-size:22px}.result-card p,.result-card small{color:var(--muted);font-size:12px}.ask-advanced,.ask-more-tasks{margin:0 0 18px}.ask-advanced>summary,.ask-more-tasks>summary{cursor:pointer;color:var(--green);font-size:12px;font-weight:750;padding:10px 0}.ask-advanced[open]>.ask-controls{margin-top:12px}.ask-controls{margin-bottom:8px}.ask-scope-note{margin:0 0 22px;color:var(--muted);font-size:10px;line-height:1.5}.ask-scope-note[hidden]{display:none}.ask-step-heading{display:grid;grid-template-columns:26px 1fr;gap:10px;align-items:start}.ask-step-heading>span{display:grid;place-items:center;width:24px;height:24px;border:1px solid #b8c8df;border-radius:50%;color:var(--blue);font-size:10px;font-weight:850}.ask-step-heading>div{display:flex;flex-direction:column}.ask-step-heading strong{font-size:12px}.ask-step-heading small{color:var(--muted);font-size:10px}.ask-task-tabs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));margin-top:13px;border:1px solid var(--line)}.ask-task-tabs button{min-height:48px;padding:8px;border:0;border-left:1px solid var(--line);border-top:1px solid var(--line);background:#fff;color:var(--muted);font-size:10px;font-weight:750;cursor:pointer}.ask-task-tabs button:nth-child(-n+3){border-top:0}.ask-task-tabs button:nth-child(3n+1){border-left:0}.ask-task-tabs button:hover{background:var(--blue-soft);color:var(--blue)}.ask-task-tabs button.active{background:var(--navy);color:#fff}.ask-task-tabs button:focus-visible{position:relative;z-index:1;outline:3px solid rgba(66,107,80,.25);outline-offset:1px}.ask-task-preview{padding:15px 17px;border-width:0 1px 1px;border-style:solid;border-color:var(--line);background:#f8fafc;display:grid;grid-template-columns:1fr;gap:3px}.ask-task-preview>span{color:var(--blue);font-size:8px;font-weight:850;letter-spacing:.1em}.ask-task-preview>strong{font:500 18px/1.3 Georgia,serif}.ask-task-preview>p{margin:2px 0 0;color:var(--muted);font-size:11px}.ask-review-step{margin-top:23px}.ask-question{margin-top:10px}.ask-scope-groups{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:20px}.ask-scope-group{padding-top:12px;border-top:2px solid var(--green)}.ask-scope-group.out-scope{border-color:#b76a4f}.ask-scope-group>strong{color:var(--ink);font-size:11px}.ask-scope-group ul{margin:10px 0 0;padding-left:17px}.ask-scope-group li{margin:0 0 9px;font-size:11px;line-height:1.45}.ask-scope-group.in-scope li::marker{color:var(--green)}.ask-scope-group.out-scope li::marker{color:#b76a4f}.ask-control-flow{margin-top:18px;padding:12px;border:1px solid #cfe0d8;background:#fff;color:var(--green);font-size:9px;font-weight:800;text-align:center;text-transform:uppercase;letter-spacing:.05em}
@media(max-width:900px){.brief-lead{border-right:0;border-bottom:1px solid #476656}.headline-card{border-right:0;border-bottom:1px solid var(--line)}}
@media(max-width:900px){.ask-layout{grid-template-columns:1fr}.ask-form{border-right:0;border-bottom:1px solid var(--line)}}
@media(max-width:620px){.ask-section,.performance-section,.filings-section,.context-section{padding:40px 0}.ask-controls{grid-template-columns:1fr}.ask-form,.ask-result{padding:20px}.ask-submit-row{align-items:flex-start;flex-direction:column}.ask-task-tabs{grid-template-columns:1fr 1fr}.ask-task-tabs button:nth-child(3){border-left:0}.ask-task-tabs button:nth-child(n+3){border-top:1px solid var(--line)}.ask-scope-groups{grid-template-columns:1fr}.brief-section{border-radius:4px}.reaction-grid>div{padding-left:0;border-left:0;border-top:1px solid #dbe8e1}.reaction-grid>div:first-child{border-top:0}.filing-summary-meta span:first-child{display:block}.filing-summary-meta span:nth-child(2){display:none}}
@media(max-width:760px){.page-nav{top:70px;display:block;margin-left:-14px;margin-right:-14px;padding:10px 14px;border-left:0;border-right:0}.page-nav>div:first-child{display:none}.page-nav-links{grid-auto-columns:minmax(95px,1fr)}.page-nav-links a{padding:9px}.page-nav-links a span{display:none}}
.brief-reading,.brief-limit{grid-column:1/-1}.brief-limit{background:#2b4036}.brief-lead a,.brief-numbers>a,.brief-lead .brief-card-heading+a{display:inline-block;margin-top:10px;color:#daefc6;font-size:10px;text-decoration:none;border-bottom:1px solid #6e8290}#earnings,#brief,#ask,#performance,#filings,#context,#page-nav{scroll-margin-top:150px}.filing-lead-header{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:12px 16px;align-items:center;padding:18px 20px;border-bottom:1px solid var(--line)}.filing-lead-header .eyebrow{margin:0 0 4px}.filing-lead-header h3{margin:0;font-size:18px;line-height:1.25}.filing-lead-header small{color:var(--muted)}.filing-lead-header a{color:var(--blue);font-size:11px;font-weight:750;text-decoration:none}.filing-lead .filing-body{border-top:0}#ask-retry,#ask-stop{min-width:0;border:1px solid var(--line);background:#fff;color:var(--ink)}.ask-submit-row>span.notice{color:var(--muted)}@media(max-width:900px){.filing-lead-header{grid-template-columns:auto 1fr;align-items:start}.filing-lead-header a{grid-column:1/-1}}
@media(max-width:900px){.brief-grid{grid-template-columns:1fr}.brief-lead,.brief-numbers,.brief-reading,.brief-limit{grid-column:1/-1}}
/* Shared with josephjwang.com: ivory paper, forest ink, lime highlights. */
:root{--paper:#f5f4ec;--panel:#fafaf5;--ink:#183c35;--muted:#657567;--line:#d8ddd3;--blue:#426b50;--blue-soft:#e9efdf;--navy:#183c35}
body{font-family:Arial,"PingFang SC","Microsoft YaHei",sans-serif}
h1,h2{letter-spacing:-.035em}h1 em{color:#6b8051}
:where(a,button,input,select,textarea):focus-visible{outline:2px solid #426b50;outline-offset:4px}
.company-link,.method-links a,.company-directory{background:var(--panel);border-radius:8px}
.company-link:hover,.directory-link:hover,.method-links a:hover{background:#edf1e4}
.topbar,.page-nav{background:rgba(245,244,236,.96)}
.brief-section{background:#183c35}.brief-limit{background:#2b4036}
.index-brand>span,.brand-mark{background:#183c35;color:#daef9e}
@media(max-width:650px){.index-topbar{align-items:flex-start;gap:16px;flex-wrap:wrap}.index-topbar>div{flex-wrap:wrap;gap:12px}}
.index-topbar{gap:22px;flex-wrap:wrap}.index-topbar>div{flex-wrap:wrap;justify-content:flex-end}.index-hero h1{font-size:clamp(42px,6.8vw,72px);line-height:1.06}.index-hero .lede{font-size:17px;line-height:1.7}.company-search{max-width:720px}.companies{margin-top:24px}.company-link{padding:24px}.method-note{margin-top:42px}.method-links a{padding:22px}.company-directory{margin-top:32px}.foot{padding-top:24px;border-top:1px solid var(--line)}
@media(max-width:650px){.index-topbar>div{justify-content:flex-start}.index-hero h1{font-size:44px}.method-links{grid-template-columns:1fr}.index-topbar{gap:18px}main{padding-top:28px}}


"""


def _index_css() -> str:
    return """
:root{--ink:#183c35;--muted:#657567;--blue:#426b50;--paper:#f5f4ec}*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--paper);color:var(--ink);font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{width:min(920px,calc(100% - 40px));padding:48px 0}.eyebrow{color:var(--blue);font-size:11px;font-weight:800;letter-spacing:.14em}h1{margin:22px 0;font:500 clamp(48px,8vw,86px)/.98 Georgia,serif;letter-spacing:-.05em}h1 em{color:var(--blue);font-weight:500}.lede{max-width:660px;color:var(--muted);font-size:19px}.companies{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:55px}.company-link{padding:25px;border:1px solid #d8ddd3;border-radius:14px;background:#fff;text-decoration:none;color:var(--ink);display:flex;flex-direction:column;transition:transform .2s,box-shadow .2s}.company-link:hover{transform:translateY(-3px);box-shadow:0 16px 40px rgba(20,38,52,.1)}.company-link span{font:500 30px Georgia,serif}.company-link small{margin-top:25px;color:var(--blue)}.foot{margin-top:30px;color:var(--muted);font-size:11px}@media(max-width:650px){main{padding:50px 0}.companies{grid-template-columns:1fr}.company-link{padding:18px}.company-link small{margin-top:8px}}
.company-search{max-width:660px;margin-top:34px}.company-search label{display:block;margin-bottom:8px;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.08em}.search-row{display:grid;grid-template-columns:1fr auto;gap:8px}.search-row input{min-width:0;padding:15px 17px;border:1px solid #d8ddd3;border-radius:7px;background:#fff;color:var(--ink);font:inherit;outline:none}.search-row input:focus{border-color:var(--blue);box-shadow:0 0 0 3px rgba(66,107,80,.12)}.search-row button{padding:0 20px;border:0;border-radius:7px;background:var(--ink);color:#fff;font-weight:750;cursor:pointer}.search-status{margin:7px 2px 0;color:var(--muted);font-size:11px}.search-status.error{color:#a4432d}.featured-label{margin:30px 0 -25px;color:var(--muted);font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.1em}.companies{margin-top:35px}.company-link{padding:22px;border-radius:5px}.company-link strong{margin-top:3px;color:var(--muted);font-size:12px}.company-link small{margin-top:21px}.return-link{display:inline-block;margin-top:24px;color:var(--blue);font-weight:750;text-decoration:none}.method-note{margin-top:80px;padding:54px 0 0;border-top:1px solid #d8ddd3}.method-note h2{margin:8px 0 10px;font:500 38px/1.1 Georgia,serif;letter-spacing:-.025em}.method-note>p:not(.eyebrow){max-width:720px;color:var(--muted);font-size:16px}.method-note ol{margin:30px 0 0;padding:0;border-top:1px solid #d8ddd3;list-style:none}.method-note li{display:grid;grid-template-columns:44px 130px 1fr;gap:16px;padding:16px 0;border-bottom:1px solid #d8ddd3}.method-note li span{color:var(--blue);font-weight:800}.method-note li small{color:var(--muted)}.method-tech{padding-top:18px;font-size:13px!important}.method-tech strong{color:var(--ink)}.method-links{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px;margin:26px 0 0}.method-links a{display:block;padding:18px 20px;border:1px solid #d8ddd3;background:#fff;text-decoration:none;transition:border-color .15s,background .15s}.method-links a:hover{border-color:var(--blue);background:#edf1e4}.method-links strong{display:block;color:var(--blue);font-size:14px;font-weight:800}.method-links small{display:block;margin-top:6px;color:var(--muted);font-size:12px;line-height:1.5}.topbar-link{color:var(--ink);font-size:11px;font-weight:750;text-decoration:none;border-bottom:1px solid rgba(66,107,80,.4);padding-bottom:2px;white-space:nowrap}.topbar-link:hover{color:var(--blue);border-bottom-color:var(--blue)}body{display:block;font-family:"Avenir Next","Segoe UI",sans-serif}main{width:min(1040px,calc(100% - 40px));margin:0 auto}@media(max-width:650px){.search-row{grid-template-columns:1fr}.search-row button{padding:14px}.method-note{margin-top:55px;padding-top:36px}.method-note li{grid-template-columns:36px 1fr}.method-note li small{grid-column:2}}
.index-language-toggle{float:right;margin-top:-34px;padding:7px 12px;border:1px solid #d8ddd3;border-radius:999px;background:#fff;color:var(--ink);font:750 11px/1.2 "Avenir Next","Segoe UI",sans-serif;cursor:pointer}.index-language-toggle:hover{border-color:#aebbc0;color:var(--blue)}.index-language-toggle:focus-visible{outline:3px solid rgba(66,107,80,.16);outline-offset:2px}
.index-topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:28px;padding-bottom:16px;border-bottom:1px solid #d8ddd3}.index-brand{display:flex;align-items:center;gap:10px;color:var(--ink);text-decoration:none}.index-brand>span{display:grid;place-items:center;width:32px;height:32px;border-radius:8px;background:var(--ink);color:#fff;font-size:10px;font-weight:850}.index-brand strong{font-size:13px}.index-topbar>div{display:flex;align-items:center;gap:14px}.index-topbar small{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.08em}.index-language-toggle{float:none;margin:0}.index-hero{max-width:790px}.index-hero h1{margin:14px 0 12px}.company-search{margin-top:22px}.method-note{margin:32px 0 8px;padding:22px 0 0;border:0;border-top:1px solid #d8ddd3;background:transparent}.method-note h2{margin:6px 0 8px;font:500 28px/1.15 Georgia,serif}.method-note>p:not(.eyebrow){max-width:720px;color:var(--muted);font-size:14px}.method-note ol{margin:18px 0 0}.method-tech-note{margin-top:10px}.method-tech-note>summary{color:var(--blue);font-size:11px;font-weight:800;cursor:pointer}.method-tech-note .method-tech{margin:10px 0 0;padding-top:0}.featured-label{margin:28px 0 -12px}@media(max-width:650px){.index-topbar{margin-bottom:22px}.index-topbar small{display:none}.method-note{margin-top:24px;padding-top:18px}.method-note h2{font-size:24px}}
.company-directory{margin-top:56px;border:1px solid #d8ddd3;background:#fff}.company-directory>summary{list-style:none;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:24px 26px;cursor:pointer}.company-directory>summary::-webkit-details-marker{display:none}.company-directory>summary .eyebrow{margin:0 0 5px}.company-directory>summary h2{margin:0;font:500 28px/1.1 Georgia,serif}.company-directory>summary>span{color:var(--blue);font-size:11px;font-weight:800}.company-directory[open]>summary{border-bottom:1px solid #d8ddd3}.directory-body{padding:22px 26px 26px}.directory-toolbar{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:16px}.directory-toolbar p{margin:0;color:var(--muted);font-size:11px}.directory-toolbar>div{display:flex;gap:6px}.directory-toolbar button{padding:7px 10px;border:1px solid #d8ddd3;background:#fff;color:var(--ink);font-size:10px;font-weight:750;cursor:pointer}.directory-toolbar button:disabled{opacity:.35;cursor:not-allowed}.directory-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border-top:1px solid #d8ddd3;border-left:1px solid #d8ddd3}.directory-link{min-width:0;padding:15px;border-right:1px solid #d8ddd3;border-bottom:1px solid #d8ddd3;color:var(--ink);text-decoration:none;display:grid;grid-template-columns:auto minmax(0,1fr);gap:2px 10px}.directory-link strong{font:500 18px Georgia,serif}.directory-link span{overflow:hidden;color:var(--muted);font-size:11px;text-overflow:ellipsis;white-space:nowrap}.directory-link small{grid-column:1/-1;margin-top:8px;color:var(--blue);font-size:9px}.directory-link:hover{background:#edf1e4}@media(max-width:650px){.company-directory{margin-top:38px}.company-directory>summary{align-items:flex-start;padding:20px;flex-direction:column;gap:8px}.company-directory>summary h2{font-size:24px}.directory-body{padding:18px}.directory-toolbar{align-items:flex-start;flex-direction:column}.directory-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.directory-link{display:flex;flex-direction:column;gap:2px}.directory-link small{margin-top:6px}}
/* Shared with josephjwang.com: ivory paper, forest ink, lime highlights. */
:root{--paper:#f5f4ec;--panel:#fafaf5;--ink:#183c35;--muted:#657567;--line:#d8ddd3;--blue:#426b50;--blue-soft:#e9efdf;--navy:#183c35}
body{font-family:Arial,"PingFang SC","Microsoft YaHei",sans-serif}
h1,h2{letter-spacing:-.035em}h1 em{color:#6b8051}
:where(a,button,input,select,textarea):focus-visible{outline:2px solid #426b50;outline-offset:4px}
.company-link,.method-links a,.company-directory{background:var(--panel);border-radius:8px}
.company-link:hover,.directory-link:hover,.method-links a:hover{background:#edf1e4}
.topbar,.page-nav{background:rgba(245,244,236,.96)}
.brief-section{background:#183c35}.brief-limit{background:#2b4036}
.index-brand>span,.brand-mark{background:#183c35;color:#daef9e}
@media(max-width:650px){.index-topbar{align-items:flex-start;gap:16px;flex-wrap:wrap}.index-topbar>div{flex-wrap:wrap;gap:12px}}
.index-topbar{gap:22px;flex-wrap:wrap}.index-topbar>div{flex-wrap:wrap;justify-content:flex-end}.index-hero h1{font-size:clamp(42px,6.8vw,72px);line-height:1.06}.index-hero .lede{font-size:17px;line-height:1.7}.company-search{max-width:720px}.companies{margin-top:24px}.company-link{padding:24px}.method-note{margin-top:42px}.method-links a{padding:22px}.company-directory{margin-top:32px}.foot{padding-top:24px;border-top:1px solid var(--line)}
@media(max-width:650px){.index-topbar>div{justify-content:flex-start}.index-hero h1{font-size:44px}.method-links{grid-template-columns:1fr}.index-topbar{gap:18px}main{padding-top:28px}}


"""

