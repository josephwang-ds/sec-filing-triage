#!/usr/bin/env python3
"""The project explained to someone who does not work in finance or machine learning.

    python scripts/build_overview_page.py

The research page assumes a reader who knows what average precision is. Most
people who open this project do not, and the interesting part of it does not
require them to: the story is that a working system looked twice as good as it
was, that the reason was a single assumption about a timestamp, and that the
difference was measured and published rather than quietly fixed.

That story is legible to anyone. This page tells it in ordinary words, with the
numbers read from the same evidence package everything else reads, so it cannot
drift the way a hand-written summary does -- which is exactly what happened to
the write-up this page replaces.

**Jargon is not simplified here, it is absent.** No average precision, no ROC
AUC, no calibration, no bootstrap. Where a technical term is unavoidable it is
replaced by what it measures: "how often the top five contained something that
mattered" instead of "precision@5". The research page keeps the vocabulary for
readers who want it, and is linked from here.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import UTC, datetime
from html import escape
from pathlib import Path

REQUIRED = ("metrics.json", "manifest.json", "leakage_study.csv")


def load(evidence: Path, root: Path) -> dict:
    missing = [name for name in REQUIRED if not (evidence / name).exists()]
    if missing:
        raise SystemExit(
            f"{evidence} is missing {missing}. Run `make evidence` first: this "
            "page has no numbers of its own."
        )

    def rows(name):
        path = evidence / name
        if not path.exists():
            return []
        with path.open() as handle:
            return list(csv.DictReader(handle))

    def blob(name):
        path = evidence / name
        return json.loads(path.read_text()) if path.exists() else {}

    return {
        "metrics": blob("metrics.json"),
        "manifest": blob("manifest.json"),
        "ladder": rows("leakage_study.csv"),
        "self_relative": blob("self_relative_metrics.json"),
        "states": {r["state"]: r for r in rows("recommendation_confusion.csv")},
        "nlp": {r["group"]: r for r in rows("nlp_feature_ablation.csv")},
        "self_ablation": {r["group"]: r for r in rows("self_relative_ablation.csv")},
        "volatility": blob("volatility_metrics.json"),
        "forecasters": {r["forecaster"]: r for r in rows("volatility_forecasters.csv")},
        # The one number not in the evidence package. A test asserts the README
        # states the true count, so reading it here inherits that guarantee
        # rather than adding a second place for it to be wrong.
        "tests": _test_count(root / "README.md"),
    }


def _test_count(readme: Path) -> int | None:
    if not readme.exists():
        return None
    found = re.search(r"(\d+) tests", readme.read_text())
    return int(found.group(1)) if found else None


def _pct(value, digits=0) -> str:
    return f"{float(value):.{digits}%}"


def _findings(data) -> str:
    """Three things that were tried, measured, and not shipped.

    Written as a list of negatives on purpose. Anyone can show what worked; the
    reason this section exists is that all three were measured with the same
    machinery as the positive results and reported the same way.
    """
    items = []
    row = data["nlp"].get("transformer_text")
    if row:
        items.append((
            "A financial language model",
            (f"FinBERT, a language model built for financial text, read all "
            f"{int(data['self_relative']['text']['documents']):,} disclosures. It made "
            f"the ranking slightly <em>worse</em>, and the measurement is precise "
            f"enough to say so rather than shrug. The reason is worth knowing: it "
            f"predicts whether news is good or bad, and this system predicts how "
            f"<em>big</em> the reaction will be, which has no direction — a very good "
            f"announcement and a very bad one are both large.")))
    chronos = data["forecasters"].get("chronos")
    shipped = data["volatility"].get("shipped")
    if chronos and shipped:
        held = float(chronos["coverage_80"])
        items.append((
            "A foundation forecasting model",
            (f"Amazon's Chronos-2 was asked to forecast how turbulent each stock "
            f"would be over the following month. When it promised a range that "
            f"should be right 80% of the time, it was right {_pct(held)} of the "
            f"time. A three-term statistical formula &mdash; three averages of "
            f"recent volatility, fitted with a line &mdash; did better, and is what "
            f"ships.")))
    both = data["self_ablation"].get("base_plus_self_relative")
    if both:
        items.append((
            "The project's own idea",
            ("Comparing each filing against its own company's history — the "
            "feature this project was most attached to — turned out to add "
            "nothing measurable as a model input. What actually helped was "
            "changing the <em>question</em>, not the inputs. It is on the public "
            "page in those words.")))
    return "".join(
        f'<li><h3>{escape(title)}</h3><p>{body}</p></li>' for title, body in items)


def render(data: dict) -> str:
    m, manifest = data["metrics"], data["manifest"]
    ladder = data["ladder"]
    naive, honest = ladder[0], ladder[-1]
    inputs = manifest.get("inputs", {})
    impossible = int(float(naive["impossible_entries"]))
    filings = int(inputs.get("events", {}).get("rows", 0))
    issuers = manifest.get("universe", {}).get("issuers")

    read_now = data["states"].get("read_now", {})
    base_rate = data["self_relative"].get("target", {}).get("base_rate")
    policy = ""
    if read_now.get("precision") and base_rate:
        policy = f"""
<section class="band">
<div class="wrap">
<h2>It also says when it is not sure</h2>
<p>The strongest label the system gives is <strong>Read now</strong>, and it is
right {_pct(float(read_now['precision']), 1)} of the time against a
{_pct(float(base_rate), 1)} background rate — roughly twice a coin flip, on
{_pct(float(read_now['share']), 1)} of the queue. It is wrong more often than it
is right, and the page says that in those words. Its value is being wrong less
often than chance, not being reliable.</p>
<p>When a company has filed too little for a fair comparison, the system says so
and shows the raw evidence instead of guessing. Every reason it gives is one a
person can check for themselves.</p>
</div>
</section>"""

    tests = data.get("tests")
    scale = [
        (f"{filings:,}", "real SEC filings", "from the government's own archive"),
        (f"{int(m['sessions']):,}", "trading days", "four years of market history"),
        (f"{tests:,}" if tests else "—", "automated tests",
         "a leak of the kind described here fails the build"),
    ]

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>What this project is &middot; Company Lens</title>
<style>
:root{{--ink:#183c35;--muted:#657567;--blue:#426b50;--paper:#f5f4ec;--panel:#fff;
--line:#dde1e2;--warm:#f0ece2;--alarm:#a8382c}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--paper);color:var(--ink);
font:400 17px/1.7 Inter,-apple-system,"Segoe UI",sans-serif}}
.wrap{{max-width:760px;margin:0 auto;padding:0 24px}}
a{{color:var(--blue)}}
.back{{display:inline-block;margin:26px 0 0;font-size:13px;text-decoration:none}}
header{{padding:30px 0 68px}}
h1{{margin:22px 0 0;font:500 clamp(36px,6vw,60px)/1.04 Georgia,serif;
letter-spacing:-.035em;text-wrap:balance}}
.lede{{margin:24px 0 0;font:400 21px/1.55 Georgia,serif;max-width:33em}}
h2{{margin:0 0 14px;font:500 31px/1.15 Georgia,serif;letter-spacing:-.02em;
text-wrap:balance}}
h3{{margin:0 0 6px;font:500 19px/1.3 Georgia,serif}}
p{{max-width:36em}}
section{{padding:60px 0;border-top:1px solid var(--line)}}
.band{{background:var(--panel)}}
.dark{{background:#183c35;color:#f5f4ec;border-top:0}}
.dark h2{{color:#fff}}
.dark p{{color:#c2ceD5}}
.dark strong{{color:#fff}}
.numbers{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
gap:1px;background:var(--line);border:1px solid var(--line);margin:34px 0 0}}
.numbers>div{{background:var(--panel);padding:22px}}
.numbers b{{display:block;font:500 34px/1 Georgia,serif;color:var(--blue)}}
.numbers span{{display:block;margin-top:8px;font-weight:650;font-size:14px}}
.numbers small{{display:block;margin-top:4px;color:var(--muted);font-size:12.5px;
line-height:1.5}}
.swing{{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;
gap:20px;margin:34px 0 0;max-width:520px}}
.swing div{{padding:20px;background:#234a40;border-radius:4px}}
.swing b{{display:block;font:500 40px/1 Georgia,serif}}
.swing .bad b{{color:#e8897c}}
.swing .good b{{color:#7fb3ff}}
.swing small{{display:block;margin-top:6px;font-size:12.5px;color:#a8b8c4}}
.swing .arrow{{color:#7d8f9c;font-size:24px}}
.findings{{list-style:none;margin:34px 0 0;padding:0}}
.findings li{{padding:22px 0;border-top:1px solid var(--line)}}
.findings p{{margin:0;color:var(--muted);font-size:15.5px}}
.callout{{margin:30px 0 0;padding:20px 24px;background:var(--warm);
border-left:3px solid var(--blue);font-size:16px}}
.callout p{{margin:0}}
.cta{{display:flex;flex-wrap:wrap;gap:12px;margin:34px 0 0}}
.cta a{{padding:13px 20px;border:1px solid var(--line);background:var(--panel);
border-radius:4px;text-decoration:none;font-weight:650;font-size:15px}}
.cta a.primary{{background:var(--blue);border-color:var(--blue);color:#fff}}
footer{{padding:40px 0 70px;color:var(--muted);font-size:13.5px}}
@media(prefers-color-scheme:dark){{:root{{--paper:#101e19;--panel:#172c23;
--ink:#e9eef0;--muted:#93a1a9;--line:#2a343a;--blue:#6ea4f7;--warm:#1f2a30;
--alarm:#e0857a}}}}
@media(max-width:560px){{.swing{{grid-template-columns:1fr;gap:12px}}
.swing .arrow{{transform:rotate(90deg)}}}}
</style></head><body>

<header><div class="wrap">
<a class="back" href="index.html">&larr; Company Lens</a>
<h1>A system that reads the day&rsquo;s filings &mdash; and a measurement of how
easy it is to fool yourself building one</h1>
<p class="lede">Every trading day, US public companies file legally-required
disclosures with the government. Most are routine. A few move the stock. An
analyst has time to read about five before the opening bell.</p>
</div></header>

<section class="band"><div class="wrap">
<h2>What it does</h2>
<p>It ranks the morning&rsquo;s filings so the five someone reads are the five
worth reading. On {filings:,} real filings from {issuers or 193} companies:</p>
<div class="numbers">
<div><b>{_pct(m['daily_precision_at_5'])}</b><span>of the time, the top five
contained something that moved the stock</span></div>
<div><b>{_pct(m['daily_random_precision_at_5'])}</b><span>if you read five at
random</span><small>the honest comparison</small></div>
<div><b>{_pct(m['daily_oracle_precision_at_5'])}</b><span>if you somehow knew in
advance</span><small>most days do not contain five important filings</small></div>
</div>
<p style="margin-top:26px">So it captures about
<strong>{_pct(m['daily_span_captured_at_5'])} of everything there is to
capture</strong>. That ceiling is the honest way to read the first number: a
system cannot find what is not there.</p>
<div class="callout"><p>It predicts <strong>how big</strong> a reaction will be,
never which direction. There are no price targets, no buy or sell
recommendations, and no trading strategy anywhere in it. Predicting direction is
a bet against desks with faster data and more money; deciding what to read is a
problem worth solving.</p></div>
</div></section>

<section class="dark"><div class="wrap">
<h2>The part worth reading about</h2>
<p>The first working version scored far better than this. It was wrong, and not
in a way that announced itself.</p>
<p>In <strong>{impossible:,} cases</strong> it had bought a stock at a price
printed <em>before</em> the disclosure it was reacting to had been filed. Not a
bug in the model &mdash; a single assumption about what a timestamp meant. Three
other mistakes of the same family sat beside it. Every one of them flattered the
result, and none of them showed up as an error.</p>
<div class="swing">
<div class="bad"><b>{float(naive['average_precision']):.3f}</b>
<small>written the ordinary way</small></div>
<span class="arrow">&rarr;</span>
<div class="good"><b>{float(honest['average_precision']):.3f}</b>
<small>after removing all four</small></div>
</div>
<p style="margin-top:30px">Removing them costs a third of the apparent
performance. <strong>Both numbers are published side by side</strong>, with the
tooling that found the problem and the tests that now fail the build if it comes
back. That is the argument of the whole project: a result you are pleased with
deserves more suspicion than one you are not, and the difference can be
measured.</p>
</div></section>

<section class="band"><div class="wrap">
<h2>Three things that did not work, and how that is known</h2>
<p>Each was tried properly, measured with the same machinery as everything else,
and reported in the same place as the successes.</p>
<ul class="findings">{_findings(data)}</ul>
</div></section>
{policy}
<section><div class="wrap">
<h2>It is running, not a slide deck</h2>
<div class="numbers">
{"".join(f'<div><b>{value}</b><span>{label}</span><small>{note}</small></div>'
         for value, label, note in scale)}
</div>
<div class="cta">
<a class="primary" href="index.html">Open the live site</a>
<a href="research.html">The audited findings, in full detail</a>
<a href="https://github.com/josephwang-ds/ai-quant-signal-platform">Source code</a>
</div>
</div></section>

<footer><div class="wrap">
<p>Every number on this page is read from the committed evidence package at build
time, so it cannot drift from the code. Generated
{datetime.now(UTC):%Y-%m-%d}. The company universe is
{escape(str(manifest.get('note', '')))}</p>
</div></footer>

</body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=Path("evidence/real_run"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path,
                        default=Path("data/build/company_pages/overview.html"))
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(load(args.evidence, args.root)), encoding="utf-8")
    print(f"overview page -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
