# Embedded bilingual HTML copy intentionally uses long lines and Chinese punctuation.
# ruff: noqa: E501, RUF001
"""Bilingual actual-report cards with deterministic, sourced comparisons."""

from __future__ import annotations

import html

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
