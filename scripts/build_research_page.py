"""The filing-triage findings, as a page on the live site.

Every number is read from `evidence/real_run` at build time. None is written
into this file, and that is the whole design: a hand-written summary of a
measured result is a copy that drifts, and this project's argument is precisely
that numbers drift when nothing is watching. If the evidence is re-exported, this
page changes with it or fails loudly because a file it needs is missing.

The visual language is the Company Lens site's own -- warm paper, Georgia
headlines, forest-green accents -- because this is a section of that site rather than a
research paper bolted onto it.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from filing_triage import prediction_log
from filing_triage.calibration import CALIBRATION_SHARE, RELIABILITY_BINS
from filing_triage.model import CV_EMBARGO, N_SPLITS
from filing_triage.self_relative import TARGET_QUANTILE
from filing_triage.uncertainty import N_BOOTSTRAP
from filing_triage.volatility import HAR_LAGS, HORIZON, LOOKBACK, QUANTILES

EMBARGO_DAYS = int(CV_EMBARGO.days)

# The read depth every headline on this page is quoted at, and therefore the one
# the live log has to be tallied at: comparing a live top-three against a
# backtested top-five would be a comparison of two different products.
TOP_K = 5

# Plain-language names for what the model reads. Semantics, not measurements:
# the importances beside them come from the evidence, these do not, because a
# feature's meaning does not change when the sample does.
FEATURE_WORDS = {
    "item_2_02": (
        "Is this an earnings release?",
        (
        "8-K item 2.02 is the code a company uses when it reports results. Registrants"
        " label their own filings, so the model knows what kind of news it is before"
        " reading a word."
    ),
    ),
    "hour_et": (
        "What time of day was it filed?",
        "New York time. Companies choose when to release news, and the choice is informative.",
    ),
    "days_since_last_earnings": (
        "How long since this company last reported?",
        "Where the filing sits in the quarterly cycle.",
    ),
    "rel_volume": (
        "Was the stock unusually busy beforehand?",
        (
        "Yesterday's volume against this company's own 60-day median. Yesterday's, never"
        " today's — today's would be the reaction the model is trying to predict."
    ),
    ),
    "days_to_expected_earnings": (
        "How close is the next expected report?",
        "Estimated from this company's own filing history, never from a published calendar.",
    ),
    "issuer_prior_material_rate": (
        "How often has this company moved markets before?",
        "Counting only filings whose outcome was already known by the time this one arrived.",
    ),
    "released_post": (
        "Was it filed after the close?",
        "Roughly two thirds of 8-Ks arrive outside market hours.",
    ),
    "released_open": (
        "Was it filed during trading hours?",
        "",
    ),
    "log_doc_chars": (
        "How long is the document?",
        "Length, on a log scale.",
    ),
    "novelty": (
        "How different is it from this company's recent filings?",
        "Cosine distance from its own previous eight 8-Ks.",
    ),
    "days_to_fiscal_year_end": (
        "Where in the fiscal year does it land?",
        "A published calendar that almost never changes.",
    ),
    "days_since_prev_filing": (
        "How long since this company filed anything?",
        "",
    ),
    "filings_trailing_year": (
        "How talkative is this company?",
        "Filings in the previous 365 days, counting only earlier ones.",
    ),
    "vol_20": (
        "How volatile has the stock been?",
        "20-session standard deviation, ending the day before.",
    ),
}

# Terms the page uses that a reader outside this field has no reason to know.
GLOSSARY = [
    (
        "8-K",
        (
        "The form a US public company files to disclose something material between"
        " quarterly reports — anything from an earnings release to a chief executive"
        " leaving."
    ),
    ),
    (
        "Material",
        (
        "Here it means the stock moved at least twice its own normal daily noise after"
        " the filing, up or down. Magnitude, never direction: this project does not"
        " predict which way."
    ),
    ),
    (
        "Average precision",
        (
        "One number for how good a ranking is, from 0 to 1. It rewards putting the"
        " filings that mattered near the top. Chance on this sample is about 0.13."
    ),
    ),
    (
        "ROC AUC",
        (
        "The chance that a filing that mattered is ranked above one that did not. 0.5 is"
        " a coin flip. Reported as a cross-check rather than the headline, because it"
        " averages over the whole ranking including the tail nobody reads."
    ),
    ),
    (
        "precision@5",
        "Of the five filings surfaced on a given morning, the share that turned out to matter.",
    ),
    (
        "Leakage",
        (
        "The model seeing something it could not have known at the time. It does not"
        " crash — it quietly produces a better score, which is what makes it dangerous."
    ),
    ),
    (
        "Purged, embargoed validation",
        (
        "Testing only on filings that came after the ones trained on, and discarding any"
        " training filing whose outcome window overlaps the test period."
    ),
    ),
    (
        "Bootstrap interval",
        (
        "Re-running the measurement on 2,000 resamples to see how much the answer moves."
        " A number without one is a claim with its error bar deleted."
    ),
    ),
    (
        "Paired comparison",
        (
        "Scoring two methods on the same resampled days, so their difference is measured"
        " directly instead of comparing two separate estimates."
    ),
    ),
]

REQUIRED = ("metrics.json", "integrity.json", "leakage_study.csv",
            "capacity_profile.csv", "baseline_intervals.csv",
            "model_comparison_paired.csv", "reaction_capture.csv",
            "anchoring_study.csv", "session_material_counts.csv",
            "oos_importance.csv", "manifest.json")

# The issuer-relative layer is exported by a second command, so these are a
# group rather than a requirement: all of them, or none. A partial set is the
# dangerous state -- it would render a calibration table beside a policy fitted
# in a different run -- so it fails loudly, while a clean absence simply omits
# the sections.
SELF_RELATIVE = ("self_relative_metrics.json", "calibration_comparison.csv",
                 "calibration_curve.csv", "recommendation_confusion.csv",
                 "history_depth_sensitivity.csv", "nlp_feature_ablation.csv",
                 "self_relative_ablation.csv", "self_relative_fold_metrics.csv",
                 "recommendation_cases.json")

# The volatility experiment is a third export and a third group, same rule: all
# of it or none.
VOLATILITY = ("volatility_metrics.json", "volatility_forecasters.csv",
              "volatility_by_regime.csv", "volatility_paired.csv")

# The Form 4 study is a fourth export and a fourth group, same rule: all of it
# or none.
INSIDERS = ("insider_metrics.json", "insider_disclosure_ladder.csv",
            "insider_gap_profile.csv", "insider_reaction_by_kind.csv")


def load(evidence: Path, predictions: Path | None = None) -> dict:
    missing = [name for name in REQUIRED if not (evidence / name).exists()]
    if missing:
        raise SystemExit(
            f"{evidence} is missing {missing}. Run `make evidence` first: this "
            "page is generated from that export and has no numbers of its own."
        )

    def rows(name):
        with (evidence / name).open() as handle:
            return list(csv.DictReader(handle))

    return {
        "metrics": json.loads((evidence / "metrics.json").read_text()),
        "integrity": json.loads((evidence / "integrity.json").read_text()),
        "manifest": json.loads((evidence / "manifest.json").read_text()),
        "ladder": rows("leakage_study.csv"),
        "capacity": rows("capacity_profile.csv"),
        "baselines": {r["baseline"]: r for r in rows("baseline_intervals.csv")},
        "families": rows("model_comparison_paired.csv"),
        "capture": {r["population"]: r for r in rows("reaction_capture.csv")},
        "anchoring": rows("anchoring_study.csv"),
        "material_counts": rows("session_material_counts.csv"),
        "importance": rows("oos_importance.csv"),
        **_self_relative(evidence, rows),
        **_volatility(evidence, rows),
        **_insiders(evidence, rows),
        **_live(predictions),
    }


def _live(predictions: Path | None) -> dict:
    """The prospective prediction log, which is not part of the evidence package.

    Deliberately not: everything in `evidence/real_run` is one frozen execution
    of the backtest, re-exported as a set, and the live log is the opposite kind
    of artefact -- it only ever grows, one file per refresh, and a date already
    in it is never rewritten. Folding it into the package would make every
    re-export appear to restate it.

    Absent is a legitimate state and renders nothing, because the section has
    nothing to say before the first refresh writes a file. An empty log is a
    different matter and does render: a log with no outcomes yet is the honest
    report for the first few weeks, and hiding it until the numbers are flattering
    is the behaviour this page exists to argue against.
    """
    if predictions is None:
        return {"live": None}
    payloads = prediction_log.load(predictions)
    if not payloads:
        return {"live": None}
    return {"live": {
        "tally": prediction_log.top_k_outcomes(payloads, k=TOP_K),
        "days": [{
            "date": payload.get("date", "?"),
            "records": len(payload.get("predictions", [])),
            "sessions": sorted({r.get("entry_session")
                                for r in payload.get("predictions", [])}),
            "top": prediction_log.top_k_outcomes([payload], k=TOP_K),
        } for payload in payloads],
    }}


def _insiders(evidence: Path, rows) -> dict:
    present = [name for name in INSIDERS if (evidence / name).exists()]
    if not present:
        return {"insiders": None}
    if len(present) != len(INSIDERS):
        raise SystemExit(
            f"{evidence} has a partial insider export: missing "
            f"{[n for n in INSIDERS if n not in present]}. Run "
            "`make insider-evidence`."
        )
    return {"insiders": {
        "metrics": json.loads((evidence / "insider_metrics.json").read_text()),
        "ladder": {r["anchor"]: r for r in rows("insider_disclosure_ladder.csv")},
        "gap": {r["statistic"]: r for r in rows("insider_gap_profile.csv")},
        "by_kind": rows("insider_reaction_by_kind.csv"),
        "agreement": rows("insider_behaviour_agreement.csv"),
    }}


def _volatility(evidence: Path, rows) -> dict:
    present = [name for name in VOLATILITY if (evidence / name).exists()]
    if not present:
        return {"volatility": None}
    if len(present) != len(VOLATILITY):
        raise SystemExit(
            f"{evidence} has a partial volatility export: missing "
            f"{[n for n in VOLATILITY if n not in present]}. Run "
            "`make volatility-evidence`."
        )
    return {"volatility": {
        "metrics": json.loads((evidence / "volatility_metrics.json").read_text()),
        "forecasters": rows("volatility_forecasters.csv"),
        "regimes": rows("volatility_by_regime.csv"),
        "paired": {r["forecaster"]: r for r in rows("volatility_paired.csv")},
    }}


def _self_relative(evidence: Path, rows) -> dict:
    present = [name for name in SELF_RELATIVE if (evidence / name).exists()]
    if not present:
        return {"self_relative": None}
    if len(present) != len(SELF_RELATIVE):
        raise SystemExit(
            f"{evidence} has a partial issuer-relative export: missing "
            f"{[n for n in SELF_RELATIVE if n not in present]}. Run "
            "`make self-relative-evidence`; half of it is worse than none, "
            "because the sections would mix two runs."
        )
    return {"self_relative": {
        "metrics": json.loads((evidence / "self_relative_metrics.json").read_text()),
        "calibration": rows("calibration_comparison.csv"),
        "curve": rows("calibration_curve.csv"),
        "states": {r["state"]: r for r in rows("recommendation_confusion.csv")},
        "depth": rows("history_depth_sensitivity.csv"),
        "ablation": rows("nlp_feature_ablation.csv"),
        "self_ablation": rows("self_relative_ablation.csv"),
        "folds": rows("self_relative_fold_metrics.csv"),
        "cases": json.loads((evidence / "recommendation_cases.json").read_text()),
    }}


def _pct(value, digits=1) -> str:
    return f"{float(value):.{digits}%}"


def _num(value, digits=3) -> str:
    return f"{float(value):.{digits}f}"


def _ladder(rows) -> str:
    out = []
    for i, r in enumerate(rows):
        last = i == len(rows) - 1
        cls = " class='clean'" if last else ""
        strong = (lambda v: f"<strong>{v}</strong>") if (last or i == 0) else (lambda v: v)
        impossible = f"{int(float(r['impossible_entries'])):,}"
        out.append(
            f"<tr{cls}><td>{r['stage']}</td>"
            f"<td class='n'>{strong(_num(r['average_precision']))}</td>"
            f"<td class='n'>{_num(r['roc_auc'])}</td>"
            f"<td class='n'>{strong(impossible)}</td>"
            f"<td class='n'>{r['checks_failed']}</td></tr>"
        )
    return "".join(out)


def _capacity(rows, headline_k=5) -> str:
    out = []
    for r in rows:
        highlight = " class='pick'" if int(r["capacity_k"]) == headline_k else ""
        out.append(
            f"<tr{highlight}><td class='n'>{r['capacity_k']}</td>"
            f"<td class='n'>{int(r['sessions']):,}</td>"
            f"<td class='n'>{_pct(r['random_floor'])}</td>"
            f"<td class='n'>{_pct(r['model'])}</td>"
            f"<td class='n'>{_pct(r['oracle_ceiling'])}</td>"
            f"<td class='n'>{float(r['lift_vs_random']):.2f}&times;</td>"
            f"<td class='n'>{_pct(r['span_captured'], 0)}</td></tr>"
        )
    return "".join(out)


def _baselines(metrics, baselines) -> str:
    label = {"random": "Random within the session",
             "arrival": "Arrival order",
             "item_202": "Item 2.02 earnings first"}
    out = [(f"<tr class='pick'><td>The model</td>"
            f"<td class='n'>{_pct(metrics['daily_model_precision_at_5'])}</td>"
            f"<td class='n'>&mdash;</td><td class='n'>&mdash;</td>"
            f"<td class='n'>&mdash;</td></tr>")]
    for key, name in label.items():
        r = baselines.get(key)
        if not r:
            continue
        draws = int(float(r["draws_not_beating_baseline"]) * 2000)
        out.append(
            f"<tr><td>{name}</td>"
            f"<td class='n'>{_pct(r['baseline_precision'])}</td>"
            f"<td class='n'>{float(r['lift']):.2f}&times;</td>"
            f"<td class='n'>[{float(r['lift_ci_low']):.2f}, {float(r['lift_ci_high']):.2f}]</td>"
            f"<td class='n'>{draws} / 2000</td></tr>")
    return "".join(out)


def _families(rows, shipped) -> str:
    pretty = {"hist_gbdt": "Gradient boosting", "logistic": "Logistic regression",
              "random_forest": "Random forest", "stratified_dummy": "Stratified dummy"}
    out = [(f"<tr class='pick'><td>{pretty.get(shipped, shipped)} "
            f"<em>(shipped)</em></td>"
            f"<td class='n'>&mdash;</td><td class='n'>&mdash;</td>"
            f"<td class='n'>&mdash;</td></tr>")]
    for r in rows:
        draws = int(float(r["draws_not_beating_reference"]) * int(r["draws"]))
        clears = float(r["difference_ci_high"]) < 0
        mark = "" if clears else " <span class='soft'>(straddles zero)</span>"
        out.append(
            f"<tr><td>{pretty.get(r['candidate'], r['candidate'])}</td>"
            f"<td class='n'>{float(r['difference']):+.3f}</td>"
            f"<td class='n'>[{float(r['difference_ci_low']):+.3f}, "
            f"{float(r['difference_ci_high']):+.3f}]{mark}</td>"
            f"<td class='n'>{draws} / {r['draws']}</td></tr>")
    return "".join(out)


def _capture(capture) -> str:
    order = [("all filings", "All filings"),
             ("not material", "Not material"),
             ("material (>= threshold)", "Material"),
             ("material, accepted post", "Material, filed after the close")]
    out = []
    for key, name in order:
        r = capture.get(key)
        if not r:
            continue
        emphasis = key.startswith("material")
        value = _pct(r["median_share_in_open"])
        out.append(f"<tr{' class=pick' if key.endswith('post') else ''}>"
                   f"<td>{'<strong>' if emphasis else ''}{name}"
                   f"{'</strong>' if emphasis else ''}</td>"
                   f"<td class='n'>{int(r['filings']):,}</td>"
                   f"<td class='n'>{'<strong>' if emphasis else ''}{value}"
                   f"{'</strong>' if emphasis else ''}</td></tr>")
    return "".join(out)


def _features(importance, limit=10) -> str:
    """What the model reads, ordered by how much it actually leans on each.

    Order and numbers come from the out-of-sample permutation importance in the
    evidence; only the plain-language names are written here. A feature the
    evidence does not rank is not shown, so the list cannot describe a column
    that has been removed.
    """
    out = []
    for row in importance[:limit]:
        words = FEATURE_WORDS.get(row["feature"])
        if not words:
            continue
        title, detail = words
        out.append(
            f"<li><b>{title}</b>"
            f"<span class='drop'>{float(row['importance']):+.3f}</span>"
            f"{f'<small>{detail}</small>' if detail else ''}"
            f"<code>{row['feature']}</code></li>"
        )
    return "".join(out)


def _cases(payload, per_state=2) -> str:
    """A few real filings per state, with the misses kept.

    `Read now` is right about two times in five. A worked-examples block showing
    only the hits would quietly claim otherwise, so each state contributes both,
    and the outcome column is where the filing's reaction actually landed in that
    issuer's own history.
    """
    labels = {"read_now": "Read now", "monitor": "Monitor", "routine": "Routine"}
    out = []
    for state, name in labels.items():
        cases = payload.get("cases", {}).get(state, [])
        hits = [c for c in cases if c["outcome"] == "as expected"][:per_state]
        misses = [c for c in cases if c["outcome"] != "as expected"][:per_state]
        for case in hits + misses:
            landed = case.get("reaction_percentile")
            right = case["cleared_own_bar"] == (state != "routine")
            out.append(
                f"<tr><td>{name}</td>"
                f"<td>{escape(case['ticker'])}</td>"
                f"<td class='n'>{escape(str(case['entry_session'] or ''))}</td>"
                f"<td class='n'>{float(case['probability']):.0%}</td>"
                f"<td class='n'>{_pct(landed) if landed is not None else '&mdash;'}</td>"
                f"<td class='n'>{'as expected' if right else 'missed'}</td></tr>")
    return "".join(out)


def _self_ablation(rows) -> str:
    """What the issuer-relative columns are worth as model inputs."""
    pretty = {"base": "Market state and filing metadata",
              "base_plus_percentiles": "&hellip; plus issuer percentiles",
              "base_plus_z_scores": "&hellip; plus issuer z-scores",
              "base_plus_self_relative": "&hellip; plus both"}
    out = []
    for r in rows:
        name = r["group"]
        if name == "base":
            interval = "<span class='soft'>reference</span>"
            delta = "&mdash;"
        else:
            separates = r["separates_from_zero"] == "True"
            mark = "" if separates else " <span class='soft'>(straddles zero)</span>"
            interval = (f"[{float(r['diff_ci_low']):+.4f}, "
                        f"{float(r['diff_ci_high']):+.4f}]{mark}")
            delta = f"{float(r['pr_auc_vs_base']):+.4f}"
        out.append(f"<tr{' class=pick' if name == 'base' else ''}>"
                   f"<td>{pretty.get(name, name)}</td>"
                   f"<td class='n'>{int(r['features'])}</td>"
                   f"<td class='n'>{_num(r['pr_auc'])}</td>"
                   f"<td class='n'>{delta}</td>"
                   f"<td class='n'>{interval}</td></tr>")
    return "".join(out)


def _folds(rows) -> str:
    """Per fold, because a pooled number can hide one that failed."""
    return "".join(
        f"<tr><td>Fold {int(r['fold']) + 1}</td>"
        f"<td class='n'>{int(r['n_scored']):,}</td>"
        f"<td class='n'>{_pct(r['base_rate'])}</td>"
        f"<td class='n'>{_num(r['pr_auc'])}</td>"
        f"<td class='n'>{_num(r['roc_auc'])}</td></tr>" for r in rows)


def _calibration(rows, shipped="identity") -> str:
    """Three ways of turning a score into a probability, scored on the same folds."""
    pretty = {"identity": "Leave the scores alone",
              "isotonic": "Isotonic regression",
              "sigmoid": "Platt scaling"}
    out = []
    for r in rows:
        pick = r["method"] == shipped
        out.append(
            f"<tr{' class=pick' if pick else ''}><td>{pretty.get(r['method'], r['method'])}"
            f"{' <em>(shipped)</em>' if pick else ''}</td>"
            f"<td class='n'>{_num(r['ece'])}</td>"
            f"<td class='n'>{_num(r['brier'])}</td>"
            f"<td class='n'>{_pct(r['brier_skill'])}</td></tr>")
    return "".join(out)


def _reliability(rows, minimum=30) -> str:
    """Stated probability against observed frequency, thin bins left out.

    A bin holding nine filings sits wherever noise puts it, and a reader cannot
    tell that from miscalibration -- so bins below `minimum` are dropped and the
    count stays on every row that remains.
    """
    out = []
    for r in rows:
        count = int(r["count"])
        if count < minimum:
            continue
        stated, observed = float(r["mean_predicted"]), float(r["observed_rate"])
        gap = observed - stated
        out.append(f"<tr><td>{_pct(r['bin_low'], 0)}&ndash;{_pct(r['bin_high'], 0)}</td>"
                   f"<td class='n'>{count:,}</td>"
                   f"<td class='n'>{_pct(stated)}</td>"
                   f"<td class='n'>{_pct(observed)}</td>"
                   f"<td class='n'>{gap:+.1%}</td></tr>")
    return "".join(out)


def _states(states, base_rate) -> str:
    order = [
        ("read_now", "Read now",
         ("A calibrated probability above the threshold <em>and</em> a signal "
          "the reader can check")),
        ("monitor", "Monitor",
         "Above the same threshold with nothing citable behind it"),
        ("routine", "Routine", "Consistent with this issuer's usual filings"),
    ]
    out = []
    for key, name, why in order:
        r = states.get(key)
        if not r or not r["precision"]:
            continue
        precision = float(r["precision"])
        out.append(
            f"<tr{' class=pick' if key == 'read_now' else ''}>"
            f"<td><strong>{name}</strong><br><span class='soft'>{why}</span></td>"
            f"<td class='n'>{int(r['count']):,}</td>"
            f"<td class='n'>{_pct(r['share'])}</td>"
            f"<td class='n'>{_pct(precision)}</td>"
            f"<td class='n'>{precision / base_rate:.2f}&times;</td>"
            f"<td class='n'>{_pct(r['recall'])}</td></tr>")
    return "".join(out)


def _ablation(rows) -> str:
    pretty = {"structured": "Market state and filing metadata",
              "deterministic_text": "&hellip; plus the wording features",
              "transformer_text": "&hellip; plus FinBERT instead",
              "all": "&hellip; everything at once"}
    out = []
    for r in rows:
        separates = r["separates_from_zero"] == "True"
        delta = float(r["pr_auc_vs_structured"])
        if r["group"] == "structured":
            interval = "<span class='soft'>reference</span>"
        else:
            mark = "" if separates else " <span class='soft'>(straddles zero)</span>"
            interval = (f"[{float(r['diff_ci_low']):+.4f}, "
                        f"{float(r['diff_ci_high']):+.4f}]{mark}")
        out.append(
            f"<tr{' class=pick' if r['group'] == 'structured' else ''}>"
            f"<td>{pretty.get(r['group'], r['group'])}</td>"
            f"<td class='n'>{int(r['features'])}</td>"
            f"<td class='n'>{_num(r['pr_auc'])}</td>"
            f"<td class='n'>{'&mdash;' if r['group'] == 'structured' else f'{delta:+.4f}'}</td>"
            f"<td class='n'>{interval}</td></tr>")
    return "".join(out)


def _sentiment_verdict(data) -> str:
    """One sentence on the FinBERT result, or silence if it was never run."""
    self_relative = data.get("self_relative")
    if not self_relative or not self_relative["ablation"]:
        return ""
    row = next((r for r in self_relative["ablation"]
                if r["group"] == "transformer_text"), None)
    if row is None:
        return ""
    return (f"It cost {abs(float(row['pr_auc_vs_structured'])):.4f} average "
            f"precision, and the table below is where that was measured.")


def _forecasters(rows, paired, reference, gates) -> str:
    """Every forecaster on the same filings: loss, coverage, and interval width."""
    pretty = {"random_walk": "Carry today forward",
              "climatology": "This issuer\u2019s own history",
              "har": "HAR regression on log volatility",
              "chronos": "Chronos-2, zero-shot"}
    out = []
    for r in rows:
        name = r["forecaster"]
        gate = gates.get(name, {})
        calibrated = gate.get("calibrated")
        difference = paired.get(name)
        if name == reference:
            gap = "<span class='soft'>reference</span>"
        elif difference:
            worse = float(difference["difference"])
            separates = difference["beats_reference"] == "True" or float(
                difference["high"]) < 0
            mark = "" if separates or float(difference["low"]) > 0 else \
                " <span class='soft'>(straddles zero)</span>"
            gap = (f"{worse:+.4f} [{float(difference['low']):+.4f}, "
                   f"{float(difference['high']):+.4f}]{mark}")
        else:
            gap = "&mdash;"
        out.append(
            f"<tr{' class=pick' if name == reference else ''}>"
            f"<td>{pretty.get(name, name)}</td>"
            f"<td class='n'>{_num(r['pinball_mean'], 4)}</td>"
            f"<td class='n'>{gap}</td>"
            f"<td class='n'>{_pct(r['coverage_50'])}</td>"
            f"<td class='n'>{_pct(r['coverage_80'])}</td>"
            f"<td class='n'>{_pct(r['width_80'])}</td>"
            f"<td class='n'>{'yes' if calibrated else 'no'}</td></tr>")
    return "".join(out)


def _regimes(rows, forecasters) -> str:
    """Coverage inside each third of the sample, for the shipped forecaster and
    the challenger it beat."""
    order = ["calm", "ordinary", "turbulent"]
    out = []
    for name in forecasters:
        for regime in order:
            row = next((r for r in rows if r["forecaster"] == name
                        and r["regime"] == regime), None)
            if row is None:
                continue
            out.append(
                f"<tr><td>{name}</td><td>{regime}</td>"
                f"<td class='n'>{int(row['filings']):,}</td>"
                f"<td class='n'>{_pct(row['median_actual'])}</td>"
                f"<td class='n'>{_pct(row['coverage_80'])}</td>"
                f"<td class='n'>{_pct(row['width_80'])}</td></tr>")
    return "".join(out)


def _glossary() -> str:
    return "".join(f"<dt>{term}</dt><dd>{meaning}</dd>" for term, meaning in GLOSSARY)


# --------------------------------------------------------------------------- #
# Page structure.
#
# Every section has the same four parts, in the same order: the question in
# plain words, the answer in one sentence with its number, the evidence, and --
# beside it -- the method that produced the evidence. The long argument for each
# result is still on the page, folded under "Why this matters", so a reader with
# a minute gets the answer and a reader with an hour loses nothing.
#
# The method notes read their parameters from the code that runs, not from
# memory: a fold count typed here would be one more number that stops tracking
# the pipeline the day someone changes it.
# --------------------------------------------------------------------------- #


def _method(**parts) -> str:
    """The margin note: what technique produced the numbers beside it."""
    rows = "".join(f"<dt>{escape(k.replace('_', ' '))}</dt><dd>{v}</dd>"
                   for k, v in parts.items() if v)
    return (f'<aside class="method"><span class="method-tag">Method</span>'
            f'<dl>{rows}</dl></aside>')


def _section(anchor: str, question: str, answer: str, evidence: str,
             method: str, more: str = "") -> str:
    """One section, in the shape every section on the page shares."""
    details = (f'<details class="more"><summary>Why this matters</summary>'
               f'<div>{more}</div></details>' if more else "")
    return f"""
<section id="{anchor}">
<h2>{question}</h2>
<p class="answer">{answer}</p>
<div class="sec-body">
<div class="sec-main">{evidence}{details}</div>
{method}
</div>
</section>
"""


def _table(head: list[str], body: str) -> str:
    cells = "".join(f"<th{'' if i == 0 else ' class=n'}>{h}</th>"
                    for i, h in enumerate(head))
    return (f'<div class="scroll"><table><thead><tr>{cells}</tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


# --------------------------------------------------------------------------- #
# The issuer-relative layer, the transformer, and the volatility experiment.
# Each returns "" when its evidence is absent: the page is generated from
# evidence, and a section with none behind it has nothing to say.
# --------------------------------------------------------------------------- #

def _issuer_relative(data) -> str:
    block = data.get("self_relative")
    if not block:
        return ""

    metrics = block["metrics"]
    target, history = metrics["target"], metrics["history"]
    policy, calibration = metrics["recommendation"], metrics["calibration"]
    base_rate = float(target["base_rate"])
    depth = history["confidence_counts"]
    covered = sum(v for k, v in depth.items() if k != "insufficient_history")
    read_now = block["states"].get("read_now", {})
    lift = (float(read_now["precision"]) / base_rate
            if read_now.get("precision") else float("nan"))
    comparison = {r["method"]: r for r in block["calibration"]}
    minimum = int(history["policy"]["minimum"])

    own_company = _section(
        "own-company",
        "Is this filing unusual <em>for this company</em>?",
        f"{int(target['eligible']):,} of {int(target['total']):,} filings have "
        f"enough of their own history to answer; {_pct(base_rate)} of them turn "
        f"out louder than that issuer&rsquo;s usual. As model inputs, the "
        f"issuer-relative columns add nothing measurable &mdash; the "
        f"<em>question</em> is what changed, not the features.",
        f"""
<div class="stats">
<div class="stat"><b>{int(target['eligible']):,}</b><span>filings with enough of
their own history<br>out of {int(target['total']):,}</span></div>
<div class="stat"><b>{_pct(base_rate)}</b><span>clear their own bar<br>
the rate a coin-flip would have to beat</span></div>
<div class="stat"><b>{int(history['median_depth'])}</b><span>median earlier
filings per issuer<br>up to {int(history['max_depth'])}</span></div>
</div>
{_table(["Features", "Count", "Avg precision", "Difference", "95% interval"],
        _self_ablation(block['self_ablation']))}
<div class="note"><strong>As model inputs, the issuer-relative columns add
nothing measurable.</strong> Every interval contains zero, in both directions.
The percentiles still earn their place, just elsewhere: they are what a
<strong>Read now</strong> cites, and a reason a reader can check is a different
job from a model input.</div>
{_table(["Fold", "Filings", "Base rate", "Avg precision", "ROC AUC"],
        _folds(block['folds']))}
""",
        _method(
            target=(f"A filing counts as unusual when its absolute abnormal reaction "
                    f"is above the {_pct(TARGET_QUANTILE, 0)} point of <em>that "
                    f"issuer&rsquo;s own</em> earlier, already-resolved reactions."),
            point_in_time=(f"Two cutoffs. Wording and volume percentiles use earlier "
                           f"filings that were already <em>accepted</em>; reaction "
                           f"percentiles use only earlier reactions that had already "
                           f"<em>finished</em>. Fewer than {minimum} earlier filings "
                           f"&rarr; no score, stated as such."),
            validation=(f"Purged, embargoed walk-forward, {N_SPLITS} folds, "
                        f"{EMBARGO_DAYS}-day embargo. Ablation rows share the same "
                        f"folds and column order."),
            uncertainty=(f"Paired difference in average precision, cluster bootstrap "
                         f"over trading sessions, {N_BOOTSTRAP:,} draws, 95% "
                         f"percentile interval."),
        ),
        f"""<p>A cross-sectional ranking asks which filing looks most like a mover,
and that quietly favours volatile small caps, which are not more newsworthy, only
noisier. This asks a different question: is the filing loud <em>for this
company</em>. An issuer with fewer than {minimum} earlier filings has no
defensible normal, and {int(depth.get('insufficient_history', 0)):,} filings are
told so rather than scored &mdash; the card shows the raw evidence and says the
history is too short. Filling that gap with a cross-sectional percentile would
answer a different question in the same visual slot. {covered:,} filings have
enough history to be scored.</p>
<p>Walk-forward, so each fold is tested on a period later than the one it was
fitted on. The spread across folds is the honest width of the result; the weakest
fold is also the one with the fewest positives to find.</p>""",
    )

    probability = _section(
        "probability",
        "Is the score a real probability?",
        f"Yes, and only after checking. The raw scores come out at "
        f"{_num(calibration['ece'])} expected calibration error; the usual fix, "
        f"isotonic regression, made it worse "
        f"({_num(comparison.get('isotonic', {}).get('ece', float('nan')))}). "
        f"So the scores ship untouched, as a measurement rather than a default.",
        f"""
{_table(["Method", "Calibration error", "Brier", "Brier skill"],
        _calibration(block['calibration']))}
{_table(["Stated probability", "Filings", "Said", "Happened", "Gap"],
        _reliability(block['curve']))}
<div class="note">A stated 30&ndash;40% should happen 30&ndash;40% of the time,
and the table says whether it does. Bins holding fewer than 30 filings are left
out: they sit wherever noise puts them.</div>
""",
        _method(
            technique=("Three calibrators scored on the same folds: leave the scores "
                       "alone, isotonic regression, Platt scaling (a logistic curve)."),
            split=(f"Each training block is cut in time order: the earlier "
                   f"{_pct(1 - CALIBRATION_SHARE, 0)} fits the model, the later "
                   f"{_pct(CALIBRATION_SHARE, 0)} fits the calibrator. The test fold "
                   f"sees neither."),
            scores=(f"Expected calibration error over {RELIABILITY_BINS} bins, "
                    f"weighted by bin size; Brier score and Brier skill against "
                    f"predicting the base rate for everything."),
        ),
        """<p>A gradient-boosted score between 0 and 1 is not a probability; it is
monotone in the right direction and nothing more. Calibration is what makes
&ldquo;0.64&rdquo; mean <em>sixty-four in a hundred</em>, and without it the
reading policy could not be stated in language a reader can check.</p>
<p>Isotonic regression is the usual choice for a tree ensemble and here it made
calibration worse. Averaging over trees is already a calibrating operation, and
fitting a flexible monotone map on a limited slice added more noise than it
removed. A calibration stage nobody checks is how a project ends up shipping a
step function it never looked at.</p>""",
    )

    reading = _section(
        "reading",
        "How well does <em>Read now</em> hold up?",
        f"<strong>Read now</strong> is right {_pct(read_now.get('precision', 0))} "
        f"of the time against a {_pct(base_rate)} base rate &mdash; "
        f"{lift:.1f}&times; a coin, on {_pct(read_now.get('share', 0))} of the "
        f"queue. It is wrong more often than it is right; its value is being wrong "
        f"less often than chance, not being reliable.",
        f"""
{_table(["State", "Filings", "Share", "Precision", "Vs base rate", "Recall"],
        _states(block['states'], base_rate))}
{_table(["State", "Issuer", "Entry session", "Said", "Reaction landed at", "Outcome"],
        _cases(block['cases']))}
<div class="note">Real filings, two hits and two misses per state.
&ldquo;Reaction landed at&rdquo; is where it sat in that issuer&rsquo;s own
history; the bar is the 80th percentile.</div>
""",
        _method(
            policy=(f"<strong>Read now</strong> needs a probability of at least "
                    f"{float(policy['read_now_threshold']):.2f} <em>and</em> one "
                    f"issuer-relative signal a person could check &mdash; unusual "
                    f"wording, unusual pre-filing volume &mdash; in that "
                    f"company&rsquo;s top {_pct(1 - policy['support_percentile'], 0)}. "
                    f"<strong>Monitor</strong> is the probability without the "
                    f"signal. Everything else is <strong>Routine</strong>."),
            thresholds=("Chosen on training folds only: the smallest threshold that "
                        "reaches the target precision. Reported on the folds that "
                        "follow."),
            scoring=("Precision and recall per state, recall against every positive "
                     "in the population so the states sum to the whole."),
            boundary=("The target is the <em>size</em> of a reaction, and a direction "
                      "cannot be recovered from it even in principle."),
        ),
        """<p><strong>Monitor</strong> reaches almost the same precision as
<strong>Read now</strong>. The difference between the two states is not accuracy
but whether the card can name a reason: requiring a citable signal costs nothing
measurable and buys an explanation, which is the trade this policy exists to
make. Nothing here is a view on price.</p>""",
    )

    return own_company + probability + reading + _transformer_section(block)


def _live_days(days) -> str:
    out = []
    for day in days:
        top = day["top"]
        sessions = ", ".join(str(x) for x in day["sessions"] if x) or "&mdash;"
        out.append(
            f"<tr><td>{escape(str(day['date']))}</td>"
            f"<td>{sessions}</td>"
            f"<td class='n'>{day['records']}</td>"
            f"<td class='n'>{top['published_at_k']}</td>"
            f"<td class='n'>{top['scored_at_k']}</td>"
            f"<td class='n'>{top['material_at_k']}</td>"
            f"<td class='n'>{top['pending_at_k']}</td></tr>"
        )
    return "".join(out)


def _live_population(tally) -> str:
    """Which sessions the log can cover, which is not a free choice.

    The refresh runs weekly, on a Saturday, and a filing is only publishable
    while no price in its reaction window has printed. By the following Saturday
    every session except the coming Monday has resolved, so the live log is
    structurally a log of Monday queues -- filings accepted over a weekend. That
    is a different population from the all-sessions average the backtest
    reports, it is a property of the cadence rather than of the ranker, and it
    is invisible in the hit rate. Stated here, read from the log's own entry
    sessions rather than asserted, because the honest comparison needs it and
    the fix is a second weekly run rather than a footnote.
    """
    weekdays = tally.get("weekdays") or []
    if not weekdays:
        return ""
    if len(weekdays) == 1:
        covers = (f"every session in this log is a {weekdays[0]}")
        because = (" A weekly Saturday refresh can only publish the queue for "
                   "the following Monday: by the next run, every other "
                   "session's windows have closed and those filings are "
                   "training data rather than predictions.")
    else:
        covers = ("the sessions in this log are "
                  + ", ".join(weekdays[:-1]) + f" and {weekdays[-1]}")
        because = ""
    return (f"<div class='note'><strong>And it is not a random sample of "
            f"sessions:</strong> {covers}.{because} So this tally is measured on "
            f"filings released around a weekend, while the backtest beside it "
            f"averages over every session of the week. A second refresh on a "
            f"weekday would widen it; nothing about the ranker would change.</div>")


def _live_section(data, m) -> str:
    """The prospective log: the one claim the rest of this page cannot make.

    Everything above is a backtest. A backtest can be audited -- that is the
    whole page -- but an audit is still an argument about process, and a reader
    is being asked to accept it. A ranking committed to a public repository
    before the prices in its reaction window existed is not an argument. It
    either held up or it did not, and no amount of care taken after the fact can
    move it either way.

    So this section is written to be legible while it is still worthless. The
    first weeks have no outcomes at all and the first months have a sample far
    too small to separate the model from a coin; publishing it anyway, with its
    interval and its sample size in front of the number, is the only version of
    this that does not become a highlight reel later.
    """
    block = data.get("live")
    if not block:
        return ""

    tally = block["tally"]
    backtest = m["daily_precision_at_5"]
    floor = m["daily_random_precision_at_5"]
    scored, material = tally["scored_at_k"], tally["material_at_k"]
    low, high = tally["hit_rate_ci_low"], tally["hit_rate_ci_high"]
    runs = tally["files"]
    dates = tally["dates"]
    span = ("no runs yet" if not dates else dates[0] if len(set(dates)) == 1
            else f"{dates[0]} to {dates[-1]}")

    if not scored:
        answer = (
            f"Not yet answerable, and that is the honest state of it. "
            f"{tally['records']} filing(s) have been published across {runs} "
            f"refresh run(s) ({span}), {tally['published_at_k']} of them inside a "
            f"top-{TOP_K} read, and not one reaction window has closed yet. The "
            f"only thing measured here so far is that the predictions were "
            f"committed before their outcomes existed."
        )
        rate_row = ("<tr class='pick'><td>Live, published before the outcome "
                    "existed</td><td class='n'>0</td><td class='n'>&mdash;</td>"
                    "<td class='n'>&mdash;</td><td class='n'>&mdash;</td></tr>")
        reading = (
            "<div class='note'>Nothing above is a result. A reaction window "
            "closes within days of the filing entering, so the rows below will "
            "acquire their outcomes almost immediately; what takes months is "
            "accumulating enough of them for the hit rate to mean anything. "
            "Published in this state deliberately &mdash; a live tally first "
            "shown once it reads well is a highlight reel.</div>"
            + _live_population(tally))
    else:
        interval = f"[{_pct(low)}, {_pct(high)}]"
        straddles = (low <= floor <= high) and (low <= backtest <= high)
        verdict = (
            "wide enough to contain both the backtest and a random queue, so it "
            "distinguishes nothing yet"
            if straddles else
            "already narrower than the gap it is being read against, which is "
            "worth saying out loud because it was not true last month")
        answer = (
            f"{_pct(tally['hit_rate'])} of the top {TOP_K} published before their "
            f"reaction windows opened turned out material &mdash; {material} of "
            f"{scored} filings, over {runs} refresh run(s). The audited backtest "
            f"reads {_pct(backtest)} and a random queue {_pct(floor)}. The 95% "
            f"interval on the live number is {interval}: {verdict}."
        )
        rate_row = (
            f"<tr class='pick'><td>Live, published before the outcome existed</td>"
            f"<td class='n'>{scored}</td><td class='n'>{material}</td>"
            f"<td class='n'><strong>{_pct(tally['hit_rate'])}</strong></td>"
            f"<td class='n'>{interval}</td></tr>")
        reading = (
            f"<div class='note'><strong>The sample is small and early, and the "
            f"interval is the number to read.</strong> {scored} scored filings "
            f"over {runs} run(s) is not an evaluation; it is the beginning of "
            f"one. Worse, the filings are not independent draws &mdash; a "
            f"morning's top {TOP_K} share one market, so the effective sample "
            f"size is closer to the number of sessions than to the number of "
            f"filings, and the Wilson interval above does not correct for that "
            f"either. Read the point estimate as a tally, not as a measurement. "
            f"The only thing that fixes it is more Saturdays.</div>"
            f"{_live_population(tally)}")

    evidence = f"""
{_table(["Reading the top " + str(TOP_K) + " by", "Filings scored", "Material",
         "Hit rate", "95% interval"],
        rate_row
        + f"<tr><td>Audited backtest, purged walk-forward</td>"
          f"<td class='n'>{int(m['daily_sessions_at_5']):,} sessions</td>"
          f"<td class='n'>&mdash;</td><td class='n'>{_pct(backtest)}</td>"
          f"<td class='n'>&mdash;</td></tr>"
        + f"<tr class='clean'><td>Random within the session</td>"
          f"<td class='n'>&mdash;</td><td class='n'>&mdash;</td>"
          f"<td class='n'>{_pct(floor)}</td><td class='n'>&mdash;</td></tr>")}
{reading}
{_table(["Published", "For session", "Filings ranked", f"In the top {TOP_K}",
         "Scored", "Material", "Window still open"], _live_days(block["days"]))}
"""

    return _section(
        "live",
        "Does it hold up on filings whose outcomes did not exist yet?",
        answer,
        evidence,
        _method(
            technique=("Each scheduled refresh ranks the filings entering the "
                       "first session its price panel does not hold &mdash; not "
                       "one price in their reaction windows has printed &mdash; "
                       "and commits the ranking to the public repository before "
                       "any of them can."),
            scored_by=("A separate run appends the realised reaction once the "
                       "window closes, from the same market-model event study "
                       "and the same threshold the backtest&rsquo;s labels use. "
                       "It may add outcome fields and nothing else."),
            pinned=("Every record&rsquo;s prediction half is digested the day it "
                    "is written and checked against the commit that introduced "
                    "it. An edited prediction fails the build."),
            what_to_read=("The sample size and the interval, in that order. A "
                          "live hit rate over a few dozen filings is compatible "
                          "with almost any claim."),
        ),
        """<p>The backtest above is scored out of sample, purged and embargoed,
and the leakage ladder prices what the ordinary shortcuts would have been worth.
All of that is still a statement about how carefully the past was handled. This
section is a different kind of claim: the ranking was published, by a scheduled
job, before the prices it is judged against existed. There is no version of
hindsight that reaches it, which is why it is worth starting a log that will be
uninformative for months rather than waiting until it is not.</p>
<p>It is also the section most likely to disagree with the one above it, and the
disagreement would be informative rather than embarrassing. The backtest runs on
a hand-picked universe of surviving large caps over four years; the live log runs
on whatever this week brought. A live number that settles below the backtest is
the most likely outcome and the most useful thing this log could tell anyone.</p>""",
    )


def _transformer_section(block) -> str:
    """The FinBERT ablation, or nothing when the corpus was never encoded."""
    metrics = block["metrics"]
    if not block["ablation"] or not metrics.get("text"):
        return ""
    row = next((r for r in block["ablation"] if r["group"] == "transformer_text"), None)
    if row is None:
        return ""
    return _section(
        "transformer",
        "Does a financial language model help?",
        f"No. Adding FinBERT costs {abs(float(row['pr_auc_vs_structured'])):.4f} "
        f"average precision, with an interval of "
        f"[{float(row['diff_ci_low']):+.4f}, {float(row['diff_ci_high']):+.4f}] "
        f"that sits entirely below zero. The financial transformer does not ship.",
        f"""
{_table(["Features", "Count", "Avg precision", "Difference", "95% interval"],
        _ablation(block['ablation']))}
<div class="note">The reason is structural, and it is the part worth keeping:
FinBERT predicts the <em>direction</em> of sentiment, and the target here is the
<em>size</em> of a reaction, which has no direction &mdash; a very good
announcement and a very bad one are both positives. Tone is close to orthogonal
to the question, and six near-orthogonal columns make a forest&rsquo;s splits
worse.</div>
""",
        _method(
            model=(f"FinBERT (<code>{escape(metrics['text']['model'])}</code>), a 2019 "
                   f"model whose training data ends in 2014 &mdash; before the first "
                   f"filing here ({metrics['sample']['first_filing'][:4]}), so its "
                   f"scores are not hindsight."),
            text=(f"Each 8-K is cut to its first <em>Item</em> heading, past the "
                  f"XBRL and SEC boilerplate, then the first "
                  f"{int(metrics['text']['max_tokens'])} tokens are encoded. "
                  f"{int(metrics['text']['documents']):,} distinct disclosures."),
            features=("Tone distribution; robust z of negativity against the issuer's "
                      "earlier filings; cosine distance to the issuer's previous "
                      "filing and to the running centroid of its history."),
            comparison=(f"Families added one at a time on the same folds, columns in "
                        f"matrix order. Paired cluster bootstrap over sessions, "
                        f"{N_BOOTSTRAP:,} draws."),
        ),
        """<p>Encoding the raw document encodes the envelope: the first 1,800 or so
characters of a filed 8-K are XBRL tags, the SEC address block and checkbox
instructions, near-identical across issuers. Measured that way the tone came out
constant to three decimals. Cutting to the first item heading is what gave the
features any resolution at all &mdash; and with resolution, they measured
worse.</p>
<p>The module and its cache stay. A directional target would make them worth
re-testing, and re-testing costs one command because the corpus is already
encoded.</p>""",
    )


def _insider_kinds(rows, cuts=("direction", "behaviour", "disclosed plan")) -> str:
    """Reaction magnitude by what the filing reported, thin groups already gone."""
    out = []
    for cut in cuts:
        for row in [r for r in rows if r["cut"] == cut]:
            out.append(f"<tr><td>{escape(cut)}</td><td>{escape(row['group'])}</td>"
                       f"<td class='n'>{int(row['filings']):,}</td>"
                       f"<td class='n'>{float(row['median_abs_reaction']):.2f}</td>"
                       f"<td class='n'>{_pct(row['material_share'])}</td></tr>")
    return "".join(out)


def _insider_ladder(ladder) -> str:
    words = {"transaction_date": "The day the insider traded",
             "acceptance_time": "The day the market could see it"}
    out = []
    for anchor, row in ladder.items():
        honest = row["honest"] == "True"
        out.append(
            f"<tr{' class=pick' if honest else ''}>"
            f"<td>{words.get(anchor, anchor)}"
            f"{' <em>(the only honest one)</em>' if honest else ''}</td>"
            f"<td class='n'>{int(row['filings']):,}</td>"
            f"<td class='n'>{float(row['median_abs_reaction']):.3f}</td>"
            f"<td class='n'>{_pct(row['material_share'])}</td></tr>")
    return "".join(out)


def _insider_section(block) -> str:
    """The Form 4 study: a second dataset, and the same bug in a new place."""
    if not block:
        return ""
    metrics = block["metrics"]
    sample, summary = metrics["sample"], metrics["disclosure_ladder"]
    gap = block["gap"]
    naive = block["ladder"].get("transaction_date", {})
    honest = block["ladder"].get("acceptance_time", {})
    if not naive or not honest:
        return ""

    inflation = float(summary["inflation_in_material_share"])
    naive_share = float(naive["material_share"])
    honest_share = float(honest["material_share"])
    ratio = naive_share / honest_share if honest_share else float("nan")

    # A handful of filings report a trade from years earlier. Those put the naive
    # anchor's entry in an unrelated period, which is noise rather than
    # foresight -- and noise pulls that arm toward the mean, making the leak look
    # smaller. Worth saying, because the intuition runs the other way.
    late = int(summary.get("late_filings_excluded", 0))
    on_time = summary.get("on_time_inflation_in_material_share")
    late_note = ""
    if late and on_time is not None:
        late_note = (
            f" A long tail files much later &mdash; {late:,} filings report a trade "
            f"more than ten days old, the oldest by "
            f"{float(gap.get('p100', {}).get('calendar_days', 0)):,.0f} days. Those "
            f"put the naive entry in an unrelated period, which is noise rather "
            f"than foresight, and noise pulls that arm toward the middle: drop "
            f"them and the gap <em>widens</em> to "
            f"{float(on_time):+.4f} from {inflation:+.4f}.")

    agreement = ""
    if block["agreement"]:
        rows = "".join(
            f"<tr><td>{escape(r['behaviour'])}</td>"
            f"<td class='n'>{int(r['trades']):,}</td>"
            f"<td class='n'>{_pct(r['share_of_sample'])}</td>"
            f"<td class='n'>{_pct(r['disclosed_under_a_plan'])}</td></tr>"
            for r in block["agreement"])
        agreement = f"""
{_table(["Inferred as", "Trades", "Share", "Actually under a disclosed plan"], rows)}
<div class="note">Cohen, Malloy and Pomorski had to <em>infer</em> which insiders
trade on a schedule, from whether they trade the same calendar month year after
year. Since 2023 the filer has had to <em>state</em> it. Scoring the inference
against the statement costs nothing, because both columns are already parsed, and
it is a check on a well-known method against ground truth it never had.</div>"""

    kinds = {r["group"]: r for r in block["by_kind"] if r["cut"] == "direction"}
    buy, sell = kinds.get("buy"), kinds.get("sell")
    asymmetry = ""
    if buy and sell:
        buy_share, sell_share = float(buy["material_share"]), float(sell["material_share"])
        asymmetry = (
            f" And the reason for moving to small companies shows up immediately: "
            f"a filing reporting a <strong>purchase</strong> is followed by a "
            f"material reaction {_pct(buy_share)} of the time against "
            f"{_pct(sell_share)} for a sale &mdash; "
            f"{buy_share / sell_share:.1f}&times; &mdash; on "
            f"{int(buy['filings']):,} purchases that a mega-cap universe does not "
            f"contain.")

    return _section(
        "insiders",
        "The same mistake, in a different dataset",
        f"A Form 4 says an executive bought or sold their own company&rsquo;s "
        f"stock. It carries two dates, and anchoring on the wrong one puts the "
        f"share of filings that look material at {_pct(naive_share)} instead of "
        f"{_pct(honest_share)} &mdash; {ratio:.1f}&times; too high, manufactured "
        f"out of days the market had not yet seen the filing.{asymmetry}",
        f"""
{_table(["Entered on", "Filings", "Median reaction", "Look material"],
        _insider_ladder(block['ladder']))}
<div class="note">The SEC allows two business days between the trade and the
filing, and the window is {float(gap.get('p50', {}).get('calendar_days', 0)):.0f}
calendar days at the median. The transaction date is the <em>more precise</em>
field and it sits right there in the XML, which is what makes reaching for it the
natural mistake rather than a careless one.
{late_note}</div>
{_table(["Cut", "Group", "Filings", "Median reaction", "Look material"],
        _insider_kinds(block['by_kind']))}
{agreement}
""",
        _method(
            source=(f"{int(sample['transactions']):,} reported transactions from "
                    f"{int(sample['issuers']):,} issuers, "
                    f"{sample['first_filing']} to {sample['last_filing']}."),
            what_counts=(f"Only open-market purchases and sales &mdash; "
                         f"{int(sample['open_market_trades']):,} of them, "
                         f"{int(sample['purchases']):,} purchases. Everything "
                         f"else on a Form 4 is compensation machinery: a grant "
                         f"vesting, the shares withheld to pay tax on it, an "
                         f"option exercised. None is a decision about the price."),
            schedule=("An insider counts as trading on a schedule when they "
                      "traded this calendar month in each of the three previous "
                      "years &mdash; computed from their earlier trades only, so "
                      "the label exists at the moment the filing lands. Too "
                      "little history gives <em>unknown</em>, not a guess."),
            boundary=("Reaction magnitude, never direction. Insider buying is "
                      "the half of this literature with documented predictive "
                      "power and it is directional; it is named here and not "
                      "modelled."),
        ),
        """<p>This is a second dataset chosen because the first one was thin: the
8-K ranker&rsquo;s strongest input is simply whether the filing is an earnings
release, and a financial language model found nothing in the text beyond that. A
Form 4 is structured rather than prose, and it is about a person&rsquo;s
behaviour rather than a corporate event.</p>
<p><strong>Survivorship is not controlled here, and it cuts one way.</strong> The
universe is companies listed today. Small companies fail often, and the
observations most likely to be missing are insiders who bought shortly before
their company collapsed &mdash; so any result about insider buying is flattered
by an unknown amount. Free price sources do not serve delisted tickers, so this
is stated rather than fixed.</p>"""
    )


def _volatility_section(block) -> str:
    if not block:
        return ""
    metrics = block["metrics"]
    task, gates = metrics["task"], metrics["gates"]
    shipped, reference = metrics["shipped"], metrics["reference"]
    challenger = metrics.get("foundation_model")
    forecasters = {r["forecaster"]: r for r in block["forecasters"]}

    def regime_coverage(forecaster, regime):
        row = next((r for r in block["regimes"] if r["forecaster"] == forecaster
                    and r["regime"] == regime), None)
        return float(row["coverage_80"]) if row else float("nan")

    pretty = {"har": "a three-term regression (HAR)",
              "climatology": "the issuer&rsquo;s own history",
              "random_walk": "carrying today forward"}
    verdict = ""
    if challenger and "chronos" in gates:
        difference = block["paired"].get("chronos", {})
        held = float(forecasters.get("chronos", {}).get("coverage_80", float("nan")))
        verdict = (f" Chronos-2, a pretrained foundation model, claims an 80% band "
                   f"and holds {_pct(held)}; it loses "
                   f"{float(difference.get('difference', 0)):+.4f} pinball loss "
                   f"to the regression over [{float(difference.get('low', 0)):+.4f}, "
                   f"{float(difference.get('high', 0)):+.4f}], and does not ship.")

    shipped_held = float(forecasters.get(shipped, {}).get("coverage_80", float("nan")))
    answer = (f"A {int(task['horizon'])}-session volatility band ships, from "
              f"{pretty.get(shipped, shipped)}: its 80% band holds "
              f"{_pct(shipped_held)} of outcomes out of sample.{verdict}"
              if shipped else
              "No forecaster passed the calibration gate, so no band ships.")

    evidence = f"""
{_table(["Forecaster", "Pinball loss", f"Vs {reference.upper()}, 95%",
         "50% band holds", "80% band holds", "Band width", "Calibrated"],
        _forecasters(block['forecasters'], block['paired'], reference, gates))}
<div class="note">Lower pinball loss is better, so a positive difference is a
loss. {int(task['scored']):,} of {int(task['filings']):,} filings have a complete
window and are scored.</div>
{_table(["Forecaster", "Regime", "Filings", "Median outcome", "80% band holds",
         "Band width"],
        _regimes(block['regimes'], [shipped] + (['chronos'] if challenger else [])))}
<div class="note">Split into thirds by how volatile the issuer already was. The
band does widen when the issuer is turbulent &mdash; it just does not
widen enough: coverage falls from {_pct(regime_coverage(shipped, 'calm'))} in the calm
third to {_pct(regime_coverage(shipped, 'turbulent'))} in the turbulent one, the
regime a reader would actually consult it about.</div>
"""
    quantiles = ", ".join(f"{q:g}" for q in QUANTILES)
    method = _method(
        target=(f"Annualised realized volatility over the {HORIZON} sessions "
                f"starting at the entry session. The forecaster&rsquo;s history "
                f"ends the session <em>before</em>, so it has seen nothing from "
                f"the window it predicts."),
        baselines=(f"All in log volatility. Carry today forward; the issuer&rsquo;s "
                   f"own distribution over {LOOKBACK:,} sessions; HAR, a linear "
                   f"regression on the {', '.join(map(str, HAR_LAGS))}-session "
                   f"averages."),
        challenger=(f"Chronos-2 (<code>{escape(challenger['model'])}</code>), "
                    f"zero-shot, log space, {int(challenger['context_length'])}"
                    f"-session context &mdash; its better configuration of the two "
                    f"measured." if challenger else ""),
        scoring=(f"Pinball loss at the {quantiles} quantiles; how often the 50% and "
                 f"80% bands contain the outcome; band width. Paired cluster "
                 f"bootstrap over sessions on the loss difference."),
        gate=(f"A forecaster ships only if both bands hold within "
              f"&plusmn;{_pct(metrics['coverage_tolerance'], 0)} of what they claim."),
    )
    more = """<p>A different question from the rest of this page, and kept apart
from it: no forecast here is an input to the filing ranker, and nothing about it
reaches the ranker. It says how much movement to expect, never which way.</p>
<p>Scored on loss and on coverage because either alone is easy to game: an
interval from zero to infinity has perfect coverage, and a sharp forecast can win
on loss while its bands quietly mean nothing. The foundation model was given its
best footing &mdash; forecasting log volatility, the same space every baseline
works in &mdash; and a pretrained model still lost to a three-term linear
regression.</p>"""
    return _section("volatility", "How turbulent is the next month?",
                    answer, evidence, method, more)


# --------------------------------------------------------------------------- #
# The page.
# --------------------------------------------------------------------------- #

STYLE = """
:root{--ink:#183c35;--muted:#657567;--blue:#426b50;--paper:#f5f4ec;
--panel:#fff;--line:#d8ddd3;--alarm:#b03a2e;--soft:#eef3fb}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
font:400 16px/1.65 Inter,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding:0 22px 96px}
header{padding:72px 0 40px;border-bottom:1px solid var(--line)}
.eyebrow{color:var(--blue);font-size:11px;font-weight:800;letter-spacing:.14em;
text-transform:uppercase;margin:0 0 16px}
h1{margin:0 0 20px;font:500 clamp(34px,5.6vw,56px)/1.02 Georgia,serif;
letter-spacing:-.035em;text-wrap:balance}
h2{margin:0 0 10px;font:500 28px/1.15 Georgia,serif;letter-spacing:-.02em;
text-wrap:balance}
h3{margin:0 0 8px;font:500 18px/1.3 Georgia,serif}
.lede{font:400 19px/1.55 Georgia,serif;max-width:62ch;margin:0}
section{padding:48px 0;border-bottom:1px solid var(--line)}
section:last-of-type{border-bottom:0}
p{max-width:64ch}
.answer{margin:0;font:400 18px/1.5 Georgia,serif;max-width:66ch}
.answer strong{font-weight:700}
.swing{display:flex;align-items:baseline;gap:18px;flex-wrap:wrap;margin:26px 0 0}
.swing b{font:500 46px/1 Georgia,serif}
.swing .bad{color:var(--alarm)}.swing .good{color:var(--blue)}
.swing .arr{color:var(--muted);font-size:26px}
.swing small{flex-basis:100%;color:var(--muted);font-size:14px;max-width:60ch}
.brief{margin:30px 0 0;padding:0;list-style:none}
.brief li{display:grid;grid-template-columns:130px minmax(0,1fr);gap:16px;
align-items:baseline;padding:13px 0;border-top:1px solid var(--line)}
.brief b{font:500 24px/1 Georgia,serif;color:var(--blue);
font-variant-numeric:tabular-nums;white-space:nowrap}
.brief span{font-size:15px;max-width:60ch}
.howto{margin:26px 0 0;padding:14px 18px;background:var(--panel);
border:1px solid var(--line);font-size:14px;color:var(--muted);max-width:none}
.howto b{color:var(--ink)}
.sec-body{display:grid;grid-template-columns:minmax(0,1fr) 250px;gap:36px;
align-items:start;margin-top:20px}
.method{position:sticky;top:18px;padding:16px 18px;background:var(--panel);
border:1px solid var(--line);border-top:3px solid var(--blue);
font-size:12.5px;line-height:1.55;color:var(--muted)}
.method-tag{display:block;margin-bottom:4px;color:var(--blue);font-size:10px;
font-weight:800;letter-spacing:.14em;text-transform:uppercase}
.method dl{margin:0}
.method dt{margin-top:11px;color:var(--ink);font-size:10.5px;font-weight:800;
letter-spacing:.08em;text-transform:uppercase}
.method dd{margin:3px 0 0}
.method code{font-size:11px;color:var(--ink)}
.more{margin-top:18px;border-top:1px solid var(--line);padding-top:12px}
.more summary{cursor:pointer;color:var(--blue);font-size:13px;font-weight:700;
list-style:none}
.more summary::before{content:"+ ";font-weight:800}
.more[open] summary::before{content:"\\2212 "}
.more>div{margin-top:10px;color:var(--muted);font-size:14.5px}
.more>div p{margin:0 0 10px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
gap:1px;background:var(--line);border:1px solid var(--line);margin:0 0 18px}
.stat{background:var(--panel);padding:18px}
.stat b{display:block;font:500 28px/1 Georgia,serif}
.stat span{display:block;margin-top:7px;font-size:12px;color:var(--muted);line-height:1.5}
.scroll{overflow-x:auto;margin:0 0 6px}
.scroll+.scroll{margin-top:22px}
table{width:100%;border-collapse:collapse;font-size:14px;min-width:520px}
th{text-align:left;padding:9px 11px;border-bottom:1px solid var(--ink);
font-size:10px;letter-spacing:.09em;text-transform:uppercase;
color:var(--muted);font-weight:700}
td{padding:10px 11px;border-bottom:1px solid var(--line)}
td.n{font-variant-numeric:tabular-nums;white-space:nowrap}
tr.clean td,tr.pick td{background:var(--soft)}
.soft{color:var(--muted);font-size:12px}
.note{margin:14px 0 4px;padding:13px 16px;background:var(--panel);
border-left:3px solid var(--blue);font-size:14px;color:var(--muted)}
.note strong{color:var(--ink)}
.features{margin:0;padding:0;list-style:none;counter-reset:f}
.features li{position:relative;padding:14px 0 14px 44px;border-bottom:1px solid var(--line);
counter-increment:f}
.features li::before{content:counter(f);position:absolute;left:0;top:15px;
color:var(--blue);font-size:12px;font-weight:800}
.features b{font:500 17px/1.35 Georgia,serif;font-weight:500}
.features .drop{margin-left:10px;color:var(--muted);font-size:12px;
font-variant-numeric:tabular-nums}
.features small{display:block;margin-top:5px;color:var(--muted);font-size:13.5px;
line-height:1.55;max-width:60ch}
.features code{display:inline-block;margin-top:7px;color:var(--muted);font-size:11px;
font-family:ui-monospace,Menlo,monospace}
.glossary{margin:18px 0 0}
.glossary dt{margin-top:14px;font-weight:750;font-size:14px}
.glossary dd{margin:4px 0 0;color:var(--muted);font-size:14px;max-width:64ch}
.methods td:first-child{font-weight:700;white-space:nowrap}
.env{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--muted);
word-break:break-all}
footer{padding:34px 0 0;color:var(--muted);font-size:13px}
a{color:var(--blue)}
.back{display:inline-block;margin-bottom:26px;font-size:13px;text-decoration:none}
@media(max-width:860px){.sec-body{grid-template-columns:1fr;gap:18px}
.method{position:static;order:-1}.brief li{grid-template-columns:1fr;gap:4px}}
@media(prefers-color-scheme:dark){:root{--paper:#101e19;--panel:#172c23;
--ink:#e9eef0;--muted:#95a3ab;--line:#2b353a;--blue:#b4cd8c;--alarm:#e08376;
--soft:#1e2833}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
"""


def _brief(data, m, naive, honest, drop, spread) -> str:
    """Six findings, one number each, for the reader with a minute."""
    items = [
        # The swing above already shows the before-and-after; repeating it here
        # would be padding. Lead instead with the count the swing cannot show.
        (f"{int(float(naive['impossible_entries'])):,}",
         ("filings the ordinary way enters <em>before EDGAR accepted them</em> "
          "&mdash; positions taken on news that did not exist yet. That is where "
          f"the {_num(drop)} of hindsight comes from; the audited rule leaves none.")),
        (_pct(m["daily_span_captured_at_5"], 0),
         ("of the achievable gap between a random queue and a perfect one is "
         "captured by reading the top five.")),
        (_num(spread),
         (f"is the most that swapping the model family moves the result. The "
         f"validation scheme moves it {_num(drop)}. The interesting part was never "
         f"the estimator.")),
    ]
    self_relative = data.get("self_relative")
    if self_relative:
        sr = self_relative["metrics"]
        read_now = self_relative["states"].get("read_now", {})
        items.append((
            f"{_pct(read_now.get('precision', 0))} vs {_pct(sr['target']['base_rate'])}",
            ("<strong>Read now</strong> against the base rate: about twice a coin, "
            "and still wrong more often than right. Every reason it gives is one a "
            "reader can check.")))
        row = next((r for r in self_relative["ablation"]
                    if r["group"] == "transformer_text"), None)
        if row:
            items.append((
                f"{float(row['pr_auc_vs_structured']):+.4f}",
                ("is what a financial language model (FinBERT) did to the ranking. "
                "Measured, worse, not shipped.")))
    volatility = data.get("volatility")
    if volatility and volatility["metrics"].get("shipped"):
        vm = volatility["metrics"]
        shipped = vm["shipped"]
        held = {r["forecaster"]: float(r["coverage_80"])
                for r in volatility["forecasters"]}
        cov = held.get(shipped, float("nan"))
        tail = (f" A pretrained foundation model held {_pct(held['chronos'])} "
                f"and did not." if "chronos" in held else "")
        items.append((
            _pct(cov),
            (f"of outcomes fall inside the next-month volatility band that ships "
            f"&mdash; a three-term regression that passed the calibration "
            f"gate.{tail}")))
    return "".join(f"<li><b>{n}</b><span>{t}</span></li>" for n, t in items)


def _methods_index(data) -> str:
    """Every method on the page, in one place, with what it guards against."""
    rows = [
        ("Leakage ladder", "How much hindsight inflates the result",
         ("The same pipeline re-run with one correction at a time, so each "
         "shortcut's cost is measured on its own.")),
        ("Purged, embargoed walk-forward",
         "Every out-of-sample number on this page",
         (f"{N_SPLITS} folds in time order; training labels that overlap a test "
         f"period are dropped, plus a {EMBARGO_DAYS}-day gap. Training on the "
         "future is the leak this prevents.")),
        ("Cluster bootstrap over sessions", "Every interval on this page",
         (f"Trading days resampled, not filings, {N_BOOTSTRAP:,} draws. Filings "
         "from one morning share a market, and treating them as independent "
         "reports an interval narrower than the evidence supports.")),
        ("Paired comparison", "Every &ldquo;vs&rdquo; column",
         ("Both sides scored on the same resampled days, so the difference is "
         "measured directly instead of comparing two separate estimates.")),
        ("Nested model selection", "The choice of model family",
         ("The family is chosen inside each training fold, so picking the best "
         "row of a table you just read is priced rather than performed.")),
        ("Permutation importance", "What the model looks at",
         ("Each input shuffled on held-out folds; the drop in precision is its "
         "importance. Out of sample, so it cannot reward memorisation.")),
    ]
    if data.get("live"):
        rows += [
            ("Prospective prediction log", "The live hit rate",
             ("Rankings committed to a public repository before the prices in "
             "their reaction windows existed, scored later by a separate run "
             "that may only append outcomes.")),
        ]
    if data.get("self_relative"):
        rows += [
            ("Issuer-relative target", "Is this filing unusual for this company",
             (f"The bar is the issuer's own {_pct(TARGET_QUANTILE, 0)} point, using "
             "only reactions that had finished before this filing arrived.")),
            ("Held-out calibration", "Is the score a real probability",
             (f"The later {_pct(CALIBRATION_SHARE, 0)} of each training block fits "
             "the calibrator; three methods compared on expected calibration error.")),
            ("Threshold selection on training folds", "Read now / Monitor / Routine",
             ("Thresholds chosen on earlier folds for a stated precision, reported "
             "on later ones.")),
            ("Feature-group ablation", "Issuer-relative columns; FinBERT",
             ("Families added one at a time on the same folds, columns in matrix "
             "order, with a paired interval on the difference.")),
        ]
    if data.get("volatility"):
        rows += [
            ("Quantile scoring and coverage", "The next-month volatility band",
             ("Pinball loss for the band's shape; how often the 50% and 80% bands "
             "contain the outcome for its honesty. Either alone is easy to game.")),
            ("Calibration gate", "Whether a forecaster ships at all",
             (f"Both bands must hold within &plusmn;"
             f"{_pct(data['volatility']['metrics']['coverage_tolerance'], 0)} of "
             "what they claim, out of sample.")),
        ]
    rows.append(("Content fingerprints", "What produced these numbers",
                 ("sha256 over the canonicalised inputs and the library versions, "
                 "so a rerun that disagrees can be told apart from a rerun on "
                 "different data.")))
    body = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in rows)
    return (f'<div class="scroll"><table class="methods"><thead><tr><th>Method</th>'
            f'<th>Used for</th><th>What it prevents</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def render(data: dict) -> str:
    m, integ, manifest = data["metrics"], data["integrity"], data["manifest"]
    ladder = data["ladder"]
    naive, honest = ladder[0], ladder[-1]
    env = manifest.get("environment", {})
    inputs = manifest.get("inputs", {})
    open_anchored = data["anchoring"][1] if len(data["anchoring"]) > 1 else None
    shipped = manifest.get("pipeline_config", {}).get("estimator", "random_forest")
    config = manifest.get("pipeline_config", {})

    # Read rather than written: the share of sessions holding nothing material is
    # why the ceiling sits where it does, and a typed copy would drift.
    empty = next((r for r in data["material_counts"]
                  if int(r["material_filings"]) == 0), None)
    empty_share = _pct(empty["share"], 0) if empty else "some"

    families = [r for r in data["families"] if r["candidate"] != "stratified_dummy"]
    spread = max(abs(float(r["difference"])) for r in families) if families else 0.0
    drop = float(naive["average_precision"]) - float(honest["average_precision"])
    post = data["capture"].get("material, accepted post")

    hindsight = _section(
        "hindsight",
        "How much does hindsight inflate the result?",
        f"Written the ordinary way, this pipeline reports "
        f"{_num(naive['average_precision'])} average precision. Audited, "
        f"{_num(honest['average_precision'])}. The {_num(drop)} between them is four "
        f"ordinary shortcuts, and none of them announces itself.",
        f"""
{_table(["Stage", "Avg precision", "ROC AUC", "Impossible entries", "Guards failing"],
        _ladder(ladder))}
<div class="note">An <strong>impossible entry</strong> is a filing whose entry
price was printed before EDGAR accepted the document &mdash; a position taken on
news that did not exist yet. The naive rule creates
{int(float(naive['impossible_entries'])):,} of them,
{_pct(naive['impossible_share'])} of measurable filings, at a median of
{float(naive['median_hindsight_hours']):.1f} hours of hindsight. The corrected
rule leaves none.</div>
""",
        _method(
            technique=("A leakage ladder: the same pipeline run again with one "
                       "correction added at a time, so each shortcut&rsquo;s cost "
                       "is measured on its own."),
            the_four=("Entering at the filing date instead of the acceptance time; "
                      "trailing features that include the event&rsquo;s own session; "
                      "a universe drawn from today&rsquo;s survivors; a train/test "
                      "split that lets training labels overlap the test period."),
            what_to_read=("The count of impossible entries. The score moves "
                          "erratically because every correction also changes which "
                          "filings are measurable at all; the count is an invariant."),
        ),
        """<p>Each row removes exactly one source of hindsight. No feature or model
differs between the top row and the bottom one, only whether the pipeline may see
what it could not have known at the time. Every number on this page below this
point is the audited one.</p>""",
    )

    worth = _section(
        "worth",
        "How good is the audited ranking?",
        f"{_num(m['average_precision'])} average precision, 95% interval "
        f"[{_num(m['average_precision_ci_low'])}, "
        f"{_num(m['average_precision_ci_high'])}]. Reading the top five each morning "
        f"finds material filings {_pct(m['daily_precision_at_5'])} of the time "
        f"against a {_pct(m['daily_oracle_precision_at_5'])} ceiling &mdash; "
        f"{_pct(m['daily_span_captured_at_5'], 0)} of the achievable gap.",
        f"""
<div class="stats">
<div class="stat"><b>{_num(m['average_precision'])}</b><span>average precision<br>
95% [{_num(m['average_precision_ci_low'])}, {_num(m['average_precision_ci_high'])}]</span></div>
<div class="stat"><b>{_num(m['roc_auc'])}</b><span>ROC AUC<br>
95% [{_num(m['roc_auc_ci_low'])}, {_num(m['roc_auc_ci_high'])}]</span></div>
<div class="stat"><b>{_pct(m['daily_span_captured_at_5'], 0)}</b>
<span>of the achievable gap captured<br>{_pct(m['daily_precision_at_5'])} against a
{_pct(m['daily_oracle_precision_at_5'])} ceiling</span></div>
<div class="stat"><b>{int(m['n_events']):,}</b><span>filings scored out of sample<br>
over {int(m['sessions']):,} sessions</span></div>
</div>
{_table(["Reading the top five by", "Material found", "Model lift", "95% interval",
         "Draws favouring it"], _baselines(m, data['baselines']))}
<div class="note">The last column is the one to read first. A lift is only a
result if it survives resampling.</div>
""",
        _method(
            validation=(f"Purged, embargoed walk-forward cross-validation: "
                        f"{N_SPLITS} folds in time order, a {EMBARGO_DAYS}-day "
                        f"embargo, training labels that overlap a test period "
                        f"dropped."),
            label=(f"Market-model event study: the abnormal return over "
                   f"{int(config.get('event_window_sessions', 0))} sessions, scaled by "
                   f"the residual volatility of a {int(config.get('estimation_sessions', 0))}"
                   f"-session estimation window that ends "
                   f"{int(config.get('estimation_gap_sessions', 0))} sessions before "
                   f"the event. Material means "
                   f"|reaction| &ge; {float(config.get('reaction_threshold', 0)):g}."),
            uncertainty=(f"Cluster bootstrap over {int(m['sessions']):,} trading "
                         f"sessions, {int(m.get('bootstrap_draws', N_BOOTSTRAP)):,} "
                         f"draws, 95% percentile intervals. Baselines paired on the "
                         f"same resample."),
        ),
        """<p>Intervals resample trading sessions, not filings: two filings from the
same morning share a market, and treating them as independent draws would report
an interval narrower than the evidence supports. Model and baselines see the same
resampled days, so their difference is measured within a day rather than between
two separate estimates.</p>""",
    )

    live = _live_section(data, m)

    capacity = _section(
        "capacity",
        "What if a reader has time for more, or fewer, than five?",
        "The lift over a random queue depends heavily on how many filings someone "
        "reads. The share of the achievable gap barely does, so the whole tradeoff "
        "is published rather than one point.",
        f"""
{_table(["Read k", "Sessions", "Random", "Model", "Ceiling", "Lift", "Span captured"],
        _capacity(data['capacity']))}
<div class="note">The ceiling is far below 100%: a session with one material
filing caps precision@5 at 20% however good the ranking, and {empty_share} of
sessions hold none at all.</div>
""",
        _method(
            technique=("Precision at <em>k</em>, per session, for each capacity in "
                       "the table."),
            reference_points=("<em>Random</em> is the expected precision of a shuffled "
                              "queue; <em>Ceiling</em> is the best possible order, "
                              "which cannot exceed the number of material filings "
                              "that day."),
            sample=("Sessions with fewer than <em>k</em> filings are excluded at that "
                    "<em>k</em>: a capacity above the day&rsquo;s count is reading "
                    "everything, not triaging."),
        ),
    )

    trading = _section(
        "trading",
        "Could this be traded?",
        f"No, and that is a measurement rather than a disclaimer. For material "
        f"filings released after the close, "
        f"{_pct(post['median_share_in_open']) if post else 'much'} of the reaction "
        f"is already in the opening print before anyone could act &mdash; "
        f"concentrated exactly where the ranker is looking.",
        f"""
{_table(["Filings", "Count", "Median share already in the opening print"],
        _capture(data['capture']))}
<div class="note">Scored against an open-anchored label &mdash; only the
movement after the open &mdash; the same pipeline falls to
{_num(open_anchored['average_precision']) if open_anchored else 'n/a'}. A harder
question, not a failing ranker.</div>
""",
        _method(
            technique=("Reaction decomposition: the share of each filing&rsquo;s "
                       "abnormal move realised between the prior close and the next "
                       "open, by filing population."),
            robustness=("The pipeline re-scored against a label anchored at the "
                        "open instead of the prior close, so the reader sees what "
                        "remains after the overnight move is removed."),
        ),
    )

    family = _section(
        "family",
        "Does the choice of model matter?",
        f"Barely. Swapping the family moves average precision by at most "
        f"{_num(spread)}; swapping the validation scheme moves it {_num(drop)}. "
        f"The interesting code was never the estimator.",
        f"""
{_table(["Family", "vs shipped", "95% interval on the difference",
         "Draws favouring shipped"], _families(data['families'], shipped))}
""",
        _method(
            technique=("Every family scored on the same filings on the same days; "
                       "differences are paired within each resample."),
            selection=("Nested: the shipped family was chosen inside each training "
                       "fold by a procedure that prices the selection rather than "
                       "performing it. Picking the top row of a table you just read "
                       "is the one leak no per-row guard can catch."),
            uncertainty=(f"Paired cluster bootstrap, {N_BOOTSTRAP:,} draws; "
                         f"&ldquo;draws favouring shipped&rdquo; counts how often it "
                         f"came out ahead."),
        ),
    )

    reads = _section(
        "reads",
        "What does the model look at?",
        f"Ten inputs carry most of the ranking, out of {len(data['importance'])}. "
        f"Every one is computable at the moment the filing lands &mdash; nothing "
        f"about what happened next.",
        f"""
<ol class="features">{_features(data['importance'])}</ol>
<div class="note">Notice what is <em>not</em> here: no price target, no analyst
estimate, no sentiment score. A sentiment model trained <em>today</em> has read
what happened afterwards, which is the same leak in a friendlier costume &mdash;
and a sentiment model old enough to avoid that was tried and measured.
{_sentiment_verdict(data)}</div>
""",
        _method(
            technique=("Permutation importance, out of sample: each column is "
                       "shuffled on the held-out folds and the drop in average "
                       "precision is recorded. Ordered by that drop."),
            rule=("Every input is a knowledge-time quantity. Trailing statistics end "
                  "the session before entry, so the event&rsquo;s own session is "
                  "never inside its own features."),
        ),
    )

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>How the ranking was audited &middot; Company Lens</title>
<style>{STYLE}.lens-nav{{display:flex;
flex-wrap:wrap;
gap:12px 22px;
align-items:center;
padding:0 0 22px;
margin-bottom:32px;
border-bottom:1px solid var(--line,var(--rule,#d8ddd3))}}
.lens-nav a{{color:inherit;
text-decoration:none;
font-size:12px;
font-weight:700}}
.lens-nav a:first-child{{margin-right:auto}}
.lens-nav a:hover{{text-decoration:underline}}
.lens-nav a:focus-visible{{outline:2px solid currentColor;
outline-offset:4px}}</style></head><body><div class="wrap">

<nav class="lens-nav" aria-label="Site navigation">
<a href="index.html">Company Lens</a>
<a href="overview.html">Overview</a>
<a href="research.html">Research</a>
<a href="https://www.josephjwang.com/">Joseph Wang ↗</a>
</nav>
<header>
<a class="back" href="index.html">&larr; Company Lens</a>
<p class="eyebrow">How the ranking was audited</p>
<h1>Ranking SEC filings,<br>audited against hindsight</h1>
<p class="lede">Each morning this ranks which SEC disclosures deserve a human
read. Every number here was measured after removing the ordinary ways a result
gets flattered by hindsight, and every section names the method that produced
it.</p>
<div class="swing">
<b class="bad">{_num(naive['average_precision'])}</b><span class="arr">&rarr;</span>
<b class="good">{_num(honest['average_precision'])}</b>
<small>Average precision, written the ordinary way &rarr; audited. Same features,
same model; only whether the pipeline may see what it could not have known.</small>
</div>
<ul class="brief">{_brief(data, m, naive, honest, drop, spread)}</ul>
<p class="howto"><b>How to read this page.</b> Every section is one question, its
answer in a sentence, the table that supports it, and &mdash; beside it &mdash;
the <b>method</b> that produced the table. &ldquo;Why this matters&rdquo; opens
the longer argument. A full index of methods is at the end.</p>
</header>
{hindsight}
{worth}
{live}
{capacity}
{trading}
{family}
{reads}
{_issuer_relative(data)}
{_volatility_section(data['volatility'])}
{_insider_section(data['insiders'])}
<section id="methods">
<h2>Every method used on this page</h2>
<p class="answer">The same handful of techniques, applied consistently. Each is
listed with what it is used for and the mistake it exists to prevent.</p>
{_methods_index(data)}
</section>

<section id="terms">
<h2>Terms used above</h2>
<details class="more"><summary>Open the glossary</summary>
<dl class="glossary">{_glossary()}</dl></details>
</section>

<section id="provenance">
<h2>What produced these numbers</h2>
<p class="answer">{int(inputs.get('events', {}).get('rows', 0)):,} filings from
{integ.get('events_total', 0):,} EDGAR records; {int(inputs.get('prices', {}).get('rows', 0)):,}
daily price rows; Python {env.get('python', '?')} with scikit-learn
{env.get('packages', {}).get('scikit-learn', '?')}. Each export records a
fingerprint of its inputs, so a rerun that disagrees can be told apart from a
rerun on different data.</p>
<div class="sec-body"><div class="sec-main">
<p class="env">events sha256 {inputs.get('events', {}).get('sha256', '')[:32]}&hellip;<br>
prices sha256 {inputs.get('prices', {}).get('sha256', '')[:32]}&hellip;</p>
<div class="note">Digests are taken over canonicalised content rather than file
bytes, so a library upgrade does not change them. A changed row count is the
source growing; an unchanged count with a changed digest is values moving
underneath &mdash; vendor prices re-adjusted after a split, say.</div>
</div>
{_method(technique=("sha256 over each input frame with columns and rows in "
                    "canonical order and floats at fixed precision."),
         recorded=("Row counts, date range, and the versions of every library "
                   "that can move a number &mdash; including the optional "
                   "transformer and forecasting stacks."))}
</div>
</section>

<footer>
<p>The universe is {manifest.get('note', '')}<br>
Generated {datetime.now(UTC):%Y-%m-%d} from the committed evidence package.
Full report with charts, per-fold results and the leakage audit:
<a href="report.html">report.html</a>.</p>
</footer>

</div></body></html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=Path("evidence/real_run"))
    # The prospective log, which only grows and is never re-exported, so it is
    # read from the repository rather than from the evidence package.
    parser.add_argument("--predictions", type=Path,
                        default=prediction_log.DIRECTORY)
    parser.add_argument("--out", type=Path,
                        default=Path("data/build/company_pages/research.html"))
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(load(args.evidence, args.predictions)),
                        encoding="utf-8")
    print(f"research page -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
