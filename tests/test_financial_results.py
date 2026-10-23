from __future__ import annotations

from copy import deepcopy

import pytest

from company_lens.financial_results import build_financial_results
from company_lens.web.financials import financial_results_section


def _payload():
    submissions = {'filings': {'recent': {
        'form': ['10-Q'], 'reportDate': ['2026-06-30'], 'filingDate': ['2026-07-30'],
        'accessionNumber': ['0000000123-26-000001'], 'primaryDocument': ['quarter.htm'],
    }}}
    def fact(start, end, value):
        return {'start': start, 'end': end, 'val': value, 'accn': '0000000123-26-000001',
                'filed': '2026-07-30', 'form': '10-Q'}
    facts = {'facts': {'us-gaap': {
        'Revenues': {'units': {'USD': [fact('2026-04-01', '2026-06-30', 120e9),
                                      fact('2025-04-01', '2025-06-30', 100e9)]}},
        'NetIncomeLoss': {'units': {'USD': [fact('2026-04-01', '2026-06-30', 20e9),
                                           fact('2025-04-01', '2025-06-30', 25e9)]}},
    }}}
    return facts, submissions


def test_actual_quarter_compares_same_filing_and_prior_year():
    facts, submissions = _payload()
    result = build_financial_results(facts, submissions, 123)
    assert result['status'] == 'available'
    assert result['period_kind'] == 'quarterly'
    metrics = {row['id']: row for row in result['metrics']}
    assert metrics['revenue']['yoy'] == pytest.approx(.2)
    assert metrics['net_income']['yoy'] == pytest.approx(-.2)
    assert result['source_url'].endswith('/123/000000012326000001/quarter.htm')


def test_cumulative_nine_month_total_never_becomes_single_quarter():
    facts, submissions = _payload()
    facts['facts']['us-gaap']['Revenues']['units']['USD'][0]['start'] = '2026-01-01'
    result = build_financial_results(facts, submissions, 123)
    assert 'revenue' not in {row['id'] for row in result['metrics']}


def test_prior_year_from_other_accession_is_not_silently_mixed():
    facts, submissions = _payload()
    facts['facts']['us-gaap']['Revenues']['units']['USD'][1]['accn'] = 'older-filing'
    result = build_financial_results(facts, submissions, 123)
    assert result['metrics'][0]['prior_value'] is None
    assert result['metrics'][0]['yoy'] is None


@pytest.mark.parametrize('old', [0, -100])
def test_zero_or_loss_base_uses_absolute_change_not_growth_percentage(old):
    facts, submissions = _payload()
    facts['facts']['us-gaap']['Revenues']['units']['USD'][1]['val'] = old
    result = build_financial_results(facts, submissions, 123)
    assert result['metrics'][0]['yoy'] is None
    assert result['metrics'][0]['change'] == 120e9 - old


def test_old_period_amendment_does_not_displace_newer_quarter():
    facts, submissions = _payload()
    for key, value in {'form': '10-K/A', 'reportDate': '2025-12-31',
                       'filingDate': '2026-08-01', 'accessionNumber': 'amendment',
                       'primaryDocument': 'annual.htm'}.items():
        submissions['filings']['recent'][key].append(value)
    result = build_financial_results(facts, submissions, 123)
    assert result['form'] == '10-Q'
    assert result['period_end'] == '2026-06-30'


def test_financial_issuers_do_not_get_generic_revenue_comparison():
    facts, submissions = _payload()
    submissions['sic'] = '6021'
    result = build_financial_results(facts, submissions, 123)
    assert [row['id'] for row in result['metrics']] == ['net_income']


def test_missing_facts_show_actual_metadata_without_invented_numbers():
    _, submissions = _payload()
    result = build_financial_results({}, submissions, 123)
    assert result['status'] == 'metadata_only'
    assert result['metrics'] == []
    assert 'quarter.htm' in financial_results_section(result)


def test_empty_submission_is_explicitly_unavailable():
    assert build_financial_results({}, {}, 123)['status'] == 'unavailable'
    assert 'data-i18n-zh' in financial_results_section(None)


def test_rendered_card_has_bilingual_values_comparison_and_source():
    facts, submissions = _payload()
    result = build_financial_results(facts, submissions, 123)
    page = financial_results_section(result)
    assert 'id="earnings"' in page
    assert '+20.0%' in page and '-20.0%' in page
    assert '1200.00' in page.replace(',', '')
    assert result['source_url'] in page
    assert 'data-i18n-en' in page and 'data-i18n-zh' in page
    bad = deepcopy(result)
    bad['source_url'] = 'https://www.sec.gov/?x="onmouseover="alert(1)'
    assert 'x=&quot;onmouseover=' in financial_results_section(bad)


def test_annual_report_never_uses_quarterly_duration():
    facts, submissions = _payload()
    submissions['filings']['recent']['form'] = ['10-K']
    rows = facts['facts']['us-gaap']['Revenues']['units']['USD']
    for row in rows:
        row['start'] = str(int(row['end'][:4]) - 1) + '-07-01'
        row['form'] = '10-K'
    result = build_financial_results(facts, submissions, 123)
    assert result['period_kind'] == 'annual'
    assert [row['id'] for row in result['metrics']] == ['revenue']
    assert result['metrics'][0]['yoy'] == pytest.approx(.2)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_facts_are_not_rendered(value):
    facts, submissions = _payload()
    facts['facts']['us-gaap']['Revenues']['units']['USD'][0]['val'] = value
    result = build_financial_results(facts, submissions, 123)
    assert 'revenue' not in {row['id'] for row in result['metrics']}
