"""Financial question evidence preserves grain, provenance and missing comparisons."""
import json

import pytest

from company_lens.financial_context import with_financial_context
from company_lens.web.ask import build_ask_evidence
from company_lens.web.financial_evidence import financial_results_packet
from company_lens.web.financials import financial_results_section
from test_ask_evidence import _snapshot
from test_financial_context import seed


@pytest.mark.parametrize('scope', ['core', 'company', 'market', 'all'])
def test_financial_references_are_citable_in_every_scope(tmp_path, scope):
    seed(tmp_path)
    snapshot = _snapshot()
    snapshot['financial_results'] = with_financial_context(tmp_path, 'COMPANY')
    record = build_ask_evidence(snapshot)['scopes'][scope]
    packet = record['evidence']['financial_results']
    metric = packet['metrics'][0]
    reference = metric['category_reference']
    assert packet['basis'] == 'as_reported_same_filing'
    assert packet['period_kind'] == 'quarterly'
    assert packet['dates_zh']['period_end'] == '2026年6月30日'
    assert metric['yoy'] == '+12.0%'
    assert reference['median_yoy'] == '+8.0%'
    assert reference['gap'] == '+4.0 percentage points'
    assert reference['gap_zh'] == '+4.0 个百分点'
    assert reference['sample_size'] == 5
    for item in [metric, reference, *reference['members']]:
        assert item['citation'] in record['allowed_citations']
        assert record['citations'][item['citation']]['label_zh']
    assert '+4.0' in record['allowed_number_literals']
    assert '6' in record['allowed_number_literals']
    html = financial_results_section(snapshot["financial_results"])
    assert 'data-ask-task-link="results"' in html


def test_insufficient_sample_never_supplies_a_median_even_if_cached(tmp_path):
    seed(tmp_path, 4)
    report = with_financial_context(tmp_path, 'COMPANY')
    report['metrics'][0]['reference'].update(median_yoy=9.876, gap_pp=123.4)
    citations = {}
    packet = financial_results_packet(report, 'COMPANY', citations)
    reference = packet['metrics'][0]['category_reference']
    assert reference['status'] == 'unavailable'
    assert reference['sample_size'] == 4
    assert 'median_yoy' not in reference and 'gap' not in reference
    assert not any(key.startswith('source:financial_peer') for key in citations)
    assert '987.6' not in json.dumps(packet)


def test_missing_financials_have_a_citable_explanation():
    citations = {}
    packet = financial_results_packet(None, 'ABC', citations)
    assert packet['status'] == 'unavailable'
    assert packet['citation'] in citations
    assert 'metrics' not in packet


def test_loss_base_does_not_create_growth_or_reference(tmp_path):
    seed(tmp_path)
    report = with_financial_context(tmp_path, 'COMPANY')
    metric = report['metrics'][0]
    metric.update(value=-10, prior_value=-20, change=10, yoy=None, reference=None)
    packet = financial_results_packet(report, 'COMPANY', {})['metrics'][0]
    assert 'yoy' not in packet
    assert 'loss' in packet['yoy_unavailable_reason']
    assert packet['category_reference']['status'] == 'unavailable'


@pytest.mark.parametrize('bad', ['', 'number', 'citation'])
def test_function_receives_financial_evidence_and_enforces_allowlists(tmp_path, bad):
    import subprocess
    import sys
    from pathlib import Path

    from test_ask_function import HARNESS

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
    from build_vercel_output import build_vercel_output

    seed(tmp_path)
    snapshot = _snapshot()
    snapshot['financial_results'] = with_financial_context(tmp_path, 'COMPANY')
    pages = tmp_path / 'pages'
    pages.mkdir()
    for name in ('index.html', '404.html', 'abc.html'):
        (pages / name).write_text('<html></html>')
    (pages / 'abc.json').write_text(json.dumps(snapshot))
    output = build_vercel_output(pages, tmp_path / 'out')
    prelude = r'''
process.env.DASHSCOPE_API_KEY = 'test-placeholder';
process.env.KV_REST_API_URL = '';
process.env.KV_REST_API_TOKEN = '';
global.fetch = async (url, options) => {
  const input = JSON.parse(JSON.parse(options.body).messages[1].content);
  if (!input.evidence.financial_results.metrics.length) throw new Error('missing financials');
  const claim = {text: '同比 +12.0%, 样本中位数 +8.0%, 差 +4.0 个百分点。',
    citations: ['metric:financial_results.revenue', 'metric:financial_reference.revenue']};
  if (BAD === 'number') claim.text += ' 987654321%';
  if (BAD === 'citation') claim.citations.push('source:invented');
  return {ok: true, text: async () => JSON.stringify({choices: [{message: {content:
    JSON.stringify({mode: 'grounded_llm', what_changed: [claim], why_it_matters: [claim],
      uncertainties: [{text: '本站样本不是全行业。',
        citations: ['metric:financial_reference.revenue']}]})
  }}]})};
};
'''
    harness = tmp_path / 'financial-harness.js'
    harness.write_text('const BAD = ' + json.dumps(bad) + ';\n' + prelude + HARNESS)
    result = subprocess.run(
        ['node', str(harness), str(output / 'functions/api/ask.func'), 'POST',
         json.dumps({'ticker': 'ABC', 'provider': 'qwen', 'language': 'zh',
                     'scope': 'core', 'question': '财报变化是什么?'})],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    response = json.loads(result.stdout)
    assert response['status'] == (502 if bad else 200), response
    if not bad:
        citation = response['payload']['answer'][0]['citations'][0]
        assert citation['label_zh'] and citation['url'].startswith('https://www.sec.gov/')
