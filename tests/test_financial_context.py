from copy import deepcopy

import pytest

from company_lens.financial_context import with_financial_context
from company_lens.financial_results import build_financial_results, save_financial_results
from company_lens.web.financials import financial_results_section


def report(growth=.12):
    return {
        'status': 'available', 'sic': '7372', 'sic_description': 'Services-Prepackaged Software',
        'period_kind': 'quarterly', 'period_end': '2026-06-30', 'filed': '2026-08-01',
        'form': '10-Q', 'source_url': 'https://www.sec.gov/Archives/test.htm',
        'metrics': [{'id': 'revenue', 'concept': 'Revenues', 'unit': 'USD',
                     'start': '2026-04-01', 'end': '2026-06-30', 'value': 112.,
                     'prior_value': 100., 'prior_start': '2025-04-01',
                     'prior_end': '2025-06-30', 'change': 12., 'yoy': growth}],
    }


def seed(tmp_path, n=5):
    save_financial_results(report(), tmp_path, 'COMPANY')
    for i in range(n):
        save_financial_results(report(.04 + i * .02), tmp_path, f'P{i}')


def test_equal_weight_median_excludes_company_and_uses_percentage_points(tmp_path):
    seed(tmp_path)
    result = with_financial_context(tmp_path, 'COMPANY')
    ref = result['metrics'][0]['reference']
    assert ref['n'] == 5
    assert ref['median_yoy'] == pytest.approx(.08)
    assert ref['gap_pp'] == pytest.approx(4.)
    assert ref['as_of'] == '2026-08-01'
    assert all(row['ticker'] != 'COMPANY' for row in ref['members'])
    page = financial_results_section(result)
    assert '+4.0 个百分点' in page
    assert '2026-04-01' in page and '2025-04-01' in page
    assert '不是行业汇总增速' in page and 'SIC 737' in page
    assert 'Revenues' in page


@pytest.mark.parametrize('mutation', [
    {'sic': '3674'}, {'period_kind': 'annual'}, {'filed': '2026-08-02'},
    {'period_end': '2026-03-31'}, {'metric': {'concept': 'SalesRevenueNet'}},
    {'metric': {'unit': 'EUR'}}, {'metric': {'yoy': None}},
    {'metric': {'yoy': float('nan')}}, {'metric': {'start': '2026-01-01'}},
    {'metric': {'prior_end': '2025-03-31'}},
])
def test_ineligible_peers_cannot_produce_a_median(tmp_path, mutation):
    seed(tmp_path, 4)
    candidate = report()
    metric_change = mutation.get('metric')
    if metric_change:
        candidate['metrics'][0].update(metric_change)
    else:
        candidate.update(mutation)
    # Deliberately write NaN to ensure corrupt inputs cannot poison the calculation.
    if metric_change and 'yoy' in metric_change and metric_change['yoy'] != metric_change['yoy']:
        import json
        path = tmp_path / 'financial_results' / 'bad.json'
        path.write_text(json.dumps(candidate))
    else:
        save_financial_results(candidate, tmp_path, 'BAD')
    ref = with_financial_context(tmp_path, 'COMPANY')['metrics'][0]['reference']
    assert ref['n'] == 4
    assert ref['status'] == 'unavailable'
    assert ref['median_yoy'] is None and ref['gap_pp'] is None


def test_missing_sic_and_zero_base_are_explicit(tmp_path):
    seed(tmp_path)
    target = report()
    target.pop('sic')
    save_financial_results(target, tmp_path, 'COMPANY')
    ref = with_financial_context(tmp_path, 'COMPANY')['metrics'][0]['reference']
    assert ref['reason'] == 'missing_classification'
    target = report(None)
    save_financial_results(target, tmp_path, 'COMPANY')
    result = with_financial_context(tmp_path, 'COMPANY')
    assert result['metrics'][0]['reference']['reason'] == 'no_company_growth'
    assert '本公司没有可比同比增长率' in financial_results_section(result)


def test_legacy_and_missing_reports_work_without_mutating_saved_artifact(tmp_path):
    assert with_financial_context(tmp_path, 'NONE') is None
    legacy = report()
    legacy.pop('sic')
    save_financial_results(legacy, tmp_path, 'COMPANY')
    with_financial_context(tmp_path, 'COMPANY')
    from company_lens.financial_results import load_financial_results
    assert load_financial_results(tmp_path, 'COMPANY') == legacy


def test_sec_classification_is_preserved():
    from test_financial_results import _payload
    facts, submissions = _payload()
    submissions.update(sic='7372', sicDescription='Services-Prepackaged Software')
    result = build_financial_results(facts, submissions, 123)
    assert result['sic'] == '7372'
    assert result['sic_description'] == submissions['sicDescription']


def test_net_income_has_its_own_sample_and_eps_has_no_reference(tmp_path):
    seed(tmp_path)
    target = report()
    income = deepcopy(target['metrics'][0])
    income.update(id='net_income', concept='NetIncomeLoss')
    eps = deepcopy(income)
    eps.update(id='eps', unit='USD/shares', concept='EarningsPerShareDiluted')
    target['metrics'].extend([income, eps])
    save_financial_results(target, tmp_path, 'COMPANY')
    metrics = with_financial_context(tmp_path, 'COMPANY')['metrics']
    assert metrics[0]['reference']['status'] == 'available'
    assert metrics[1]['reference']['n'] == 0
    assert 'reference' not in metrics[2]


def test_multiple_share_classes_count_as_one_issuer(tmp_path):
    seed(tmp_path, 4)
    first = report(.08)
    first['cik'] = '1234'
    save_financial_results(first, tmp_path, 'CLASSA')
    save_financial_results(first, tmp_path, 'CLASSB')
    ref = with_financial_context(tmp_path, 'COMPANY')['metrics'][0]['reference']
    assert ref['n'] == 5
    assert sum(row['ticker'].startswith('CLASS') for row in ref['members']) == 1
    target = report()
    target['cik'] = '1234'
    save_financial_results(target, tmp_path, 'COMPANY')
    ref = with_financial_context(tmp_path, 'COMPANY')['metrics'][0]['reference']
    assert ref['n'] == 4


def test_old_artifacts_outside_current_coverage_are_excluded(tmp_path):
    seed(tmp_path)
    (tmp_path / 'universe.csv').write_text('ticker,name\nCOMPANY,Company\nP0,Peer 0\n')
    ref = with_financial_context(tmp_path, 'COMPANY')['metrics'][0]['reference']
    assert ref['n'] == 1
    assert ref['members'][0]['ticker'] == 'P0'
