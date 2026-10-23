# Embedded bilingual HTML copy intentionally uses long lines and Chinese punctuation.
# ruff: noqa: E501, RUF001
"""Bilingual actual-report cards with deterministic, sourced comparisons."""

from __future__ import annotations

import html

DEFINITIONS = {
    "revenue": ("Reported revenue before expenses; not stock performance.", "报告列示的收入，未扣除费用；不是股价回报。"),
    "net_income": ("Reported net income after expenses and taxes; the exact SEC concept is shown below.", "报告列示的税后净利润；具体 SEC 会计标签见下方。"),
    "eps": ("Diluted earnings per share; not total profit or a growth rate.", "考虑稀释后的每股收益；不是利润总额或增长率。"),
    "gross_profit": ("Revenue less cost of revenue, in dollars; not gross margin percent.", "收入减去营业成本的金额；不是毛利率。"),
}

LABELS = {
    "revenue": ("Revenue", "收入"),
    "net_income": ("Net income", "净利润"),
    "eps": ("Diluted EPS", "稀释每股收益"),
    "gross_profit": ("Gross profit", "毛利润"),
}


def _text(en: str, zh: str, tag: str = "span") -> str:
    return (
        f'<{tag} data-i18n-en="{html.escape(en, quote=True)}" '
        f'data-i18n-zh="{html.escape(zh, quote=True)}">{html.escape(en)}</{tag}>'
    )


def _money(value: float, unit: str, chinese: bool = False) -> str:
    if unit == "USD/shares":
        return f"{value:,.2f} 美元/股" if chinese else f"${value:,.2f} / share"
    return f"{value / 1e8:,.2f} 亿美元" if chinese else f"${value / 1e9:,.2f}B"


def _metric_context(metric: dict) -> str:
    en, zh = DEFINITIONS[metric["id"]]
    context = _text(en, zh, "p")
    context += _text(
        f"Current: {metric['start']} — {metric['end']} · {metric['unit']}",
        f"本期：{metric['start']} — {metric['end']} · {metric['unit']}", "small")
    if metric["prior_start"]:
        context += _text(
            f"Prior year: {metric['prior_start']} — {metric['prior_end']}",
            f"上年同期：{metric['prior_start']} — {metric['prior_end']}", "p")
    reference = metric.get("reference")
    if reference:
        n, minimum = reference["n"], reference["minimum"]
        if reference["status"] == "available":
            context += _text(
                f"Covered SIC {reference['sic_group']} sample median YoY: {reference['median_yoy']:+.1%} (n={n}, excluding this company). Gap: {reference['gap_pp']:+.1f} percentage points.",
                f"本站 SIC {reference['sic_group']} 类别样本同比中位数：{reference['median_yoy']:+.1%}（{n} 家，不含本公司）。差值：{reference['gap_pp']:+.1f} 个百分点。", "p")
        else:
            reasons = {
                "no_company_growth": ("No comparable company growth rate.", "本公司没有可比同比增长率。"),
                "missing_classification": ("SEC SIC classification is missing.", "缺少 SEC SIC 分类。"),
                "insufficient_sample": (f"Only {n} eligible companies; at least {minimum} required.", f"符合条件的公司仅 {n} 家，至少需要 {minimum} 家。"),
            }
            en_reason, zh_reason = reasons[reference["reason"]]
            context += _text("Category reference unavailable. " + en_reason, "暂无类别参考。" + zh_reason, "p")
        context += '<details class="metric-method"><summary>' + _text("Reference method and sources", "参考口径与来源") + '</summary>'
        context += _text(
            f"As of {reference['as_of']}. Latest cached filings only; one issuer per CIK (share classes deduplicated); SEC SIC first 3 digits, same annual/quarterly grain, exact accounting concept and currency. Period ends within 45 days; durations within 15 days. Later filings, missing comparisons and zero/loss bases excluded. Equal-weight median of company YoY rates; not aggregate industry growth, a full industry census, or a matched business peer set. Historical peer filings are not reconstructed.",
            f"截至 {reference['as_of']}。仅使用最新缓存报告，按 CIK 去重同一公司的不同股类：SEC SIC 前三位相同，年度／单季粒度、会计标签和币种相同；期末相差不超过 45 天，期间长度相差不超过 15 天。剔除之后披露、缺少同比、零基数及涉及亏损的样本。取公司同比的等权中位数，不是行业汇总增速、全行业统计或严格业务可比公司组；不重建同类公司历史报告。", "p")
        if reference["members"]:
            context += '<ul>'
            for member in reference["members"]:
                url = html.escape(member["source_url"], quote=True)
                label = html.escape(f"{member['ticker']} · {member['period_end']} · {member['yoy']:+.1%}")
                context += f'<li><a href="{url}" target="_blank" rel="noopener noreferrer">{label} ↗</a></li>'
            context += '</ul>'
        context += '</details>'
    context += '<details class="metric-method"><summary>' + _text("Metric definition", "指标口径") + '</summary>'
    context += _text(
        "YoY = current / prior-year value − 1. Compared with the same period a year ago, not the previous quarter. Percentage-point gap = company growth − sample median growth. Consolidated reported facts; company-specific accounting and business mixes may differ.",
        "同比 = 本期 ÷ 上年同期 − 1；比较去年同期，不是上一季度。百分点差 = 公司增速 − 样本中位增速。采用报告中的合并财务事实；不同公司的会计处理和业务构成仍可能不同。", "p")
    context += '<code>' + html.escape(metric["concept"]) + '</code></details>'
    return context


def financial_results_section(report: dict | None) -> str:
    heading = _text(
        "What changed in the latest financial report?", "最近财报发生了什么变化？", "h2"
    )
    if not report or report.get("status") == "unavailable":
        return (
            '<section id="earnings" aria-label="Financial results">'
            + heading
            + _text(
                "A current financial report is not available in this snapshot.",
                "当前快照尚未取得可核对的财报信息。",
                "p",
            )
            + "</section>"
        )
    kind_en, kind_zh = (
        ("Annual", "年度") if report["period_kind"] == "annual" else ("Quarterly", "季度")
    )
    summary = _text(
        f"{kind_en} period ended {report['period_end']} · filed {report['filed']} · {report['form']}",
        f"{kind_zh}截至 {report['period_end']} · 披露于 {report['filed']} · {report['form']}",
        "p",
    )
    if report.get("sic_description"):
        summary += _text(
            f"SEC industry registration: {report['sic_description']} (SIC {report.get('sic', '')}). SIC is a broad classification, not a curated peer list.",
            f"SEC 行业登记：{report['sic_description']}（SIC {report.get('sic', '')}）。SIC 是分类参考，不是人工筛选的可比公司名单。", "p")
    cards = []
    for metric in report["metrics"]:
        key, unit, value, old = metric["id"], metric["unit"], metric["value"], metric["prior_value"]
        en, zh = LABELS[key]
        if old is None:
            comparison = _text(
                "No comparable prior-year value in this filing.",
                "本次报告未提供同口径的上年同期数。",
                "p",
            )
        else:
            comparison = _text(
                f"Prior year ({metric['prior_end']}): {_money(old, unit)}",
                f"上年同期（{metric['prior_end']}）：{_money(old, unit, True)}",
                "p",
            )
            if metric["yoy"] is not None:
                comparison += _text(
                    f"Year over year: {metric['yoy']:+.1%}", f"同比：{metric['yoy']:+.1%}", "strong"
                )
            else:
                comparison += _text(
                    f"Change: {_money(metric['change'], unit)}; growth percentage withheld for zero bases or losses.",
                    f"变动：{_money(metric['change'], unit, True)}；零基数或涉及亏损时不显示增长百分比。",
                    "small",
                )
        cards.append(
            '<article class="result-card">'
            + _text(en, zh, "h3")
            + _text(_money(value, unit), _money(value, unit, True), "strong")
            + comparison
            + _metric_context(metric)
            + "</article>"
        )
    if not cards:
        cards.append(
            _text(
                "The filing is available; comparable numeric facts have not been extracted.",
                "已取得报告原文，但尚未提取可比财务数字。",
                "p",
            )
        )
    if report.get("financial_issuer"):
        cards.append(
            _text(
                "Financial issuers use different revenue definitions; generic revenue and gross-profit comparisons are omitted.",
                "金融企业的收入口径不同，本页不套用通用收入与毛利润比较。",
                "p",
            )
        )
    source = html.escape(report["source_url"], quote=True)
    return (
        '<section id="earnings" aria-label="Financial results"><div class="section-heading">'
        + heading
        + "</div>"
        + _text("Formal quarterly/annual reports (10-Q/10-K). Earnings announcements in 8-K remain under Disclosures.", "这里比较正式季报、年报（10-Q／10-K）；8-K 业绩快报仍在“公司披露”中查看。", "p")
        + summary
        + '<div class="result-grid">'
        + "".join(cards)
        + "</div>"
        + _text(
            "Values and comparisons come from this filing. Annual and quarterly periods are kept separate; cumulative 6/9-month totals are excluded from quarterly comparisons. These changes do not explain their causes or establish an investment signal.",
            "数字与同比均来自本次报告，年度与季度分开比较，季度数据不混入半年或九个月累计值。这里只展示变化，不推断原因或给出利好、利空判断。",
            "p",
        )
        + f'<a href="{source}" target="_blank" rel="noopener noreferrer">'
        + _text("Read the financial report ↗", "查看财报原文 ↗")
        + "</a></section>"
    )
