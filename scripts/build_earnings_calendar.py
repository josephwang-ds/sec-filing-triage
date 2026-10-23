# Embedded bilingual HTML copy.
# ruff: noqa: E501, RUF001
"""Keep the old calendar URL usable after moving actual results into company pages."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("data/build/company_pages/earnings.html"))
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Financial results · Company Lens</title>
<style>body{max-width:720px;margin:12vh auto;padding:28px;background:#f5f4ec;color:#183c35;font:18px/1.7 system-ui}a{color:inherit}</style></head><body>
<h1>财报信息已移至各公司页</h1>
<p>我们已移除预计财报日历。打开公司页的“财报变化”，查看实际披露的报告、可比财务数字及原文。</p>
<h2>Financial results now live on company pages</h2>
<p>The estimated calendar has been retired. Open a company to review its filed report and comparable results.</p>
<p><a href="index.html">查找公司 / Find a company →</a></p>
<p><a href="aapl.html#earnings">Apple</a> · <a href="msft.html#earnings">Microsoft</a> · <a href="nvda.html#earnings">NVIDIA</a></p>
</body></html>""",
        encoding="utf-8",
    )
    print(f"Retired calendar notice: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
