"""Publication/entry regressions; all services are simulated, never production."""
from __future__ import annotations

from datetime import timedelta
from typing import ClassVar

import pytest
from tests.test_events_a1 import NOW, _row
from tests.test_events_closure import ROOT, _run, _source
from tests.test_events_drill import _load

from company_lens.events.blob_store import (
    MemoryBlob,
    commit_path,
    pull_checkpoint,
    read_pointer,
    read_published,
)


def test_listing_etag_cannot_authorize_a_cached_old_checkpoint(tmp_path):
    class CachedBlob(MemoryBlob):
        cached = None

        def read_url(self, url):
            if self.cached and url.endswith(commit_path()):
                cached, self.cached = self.cached, None
                return cached
            return super().read_url(url)

    blob = CachedBlob()
    _run(tmp_path / 'first', blob, {'news': _source({'AAPL': [_row('AAPL', 1)]})},
         ['AAPL'], NOW, datasets=('news',))
    old = blob.read_url(blob.get_prefix(commit_path())[0]['url'])
    later = NOW + timedelta(days=1)
    _run(tmp_path / 'new', blob,
         {'news': _source({'AAPL': [_row('AAPL', 2, title='new headline')]})},
         ['AAPL'], later, datasets=('news',))
    before_page = read_published(blob, 'AAPL')
    before_checkpoint = pull_checkpoint(blob)[0]
    before_pointer = read_pointer(blob)[0]
    blob.cached = old  # list sees new ETag, GET returns old body AND old ETag
    result = _run(tmp_path / 'stale', blob,
                  {'news': _source({'AAPL': [_row('AAPL', 3, title='old writer')]})},
                  ['AAPL'], later, datasets=('news',))
    assert result.status == 'stale_writer'
    assert read_published(blob, 'AAPL') == before_page
    assert pull_checkpoint(blob)[0] == before_checkpoint
    assert read_pointer(blob)[0] == before_pointer


def test_existing_commit_without_body_etag_fails_closed(tmp_path):
    class MissingEtag(MemoryBlob):
        strip = False

        def read_url(self, url):
            body, etag = super().read_url(url)
            return body, '' if self.strip else etag

    blob = MissingEtag()
    _run(tmp_path / 'first', blob, {'news': _source({'AAPL': []})},
         ['AAPL'], NOW, datasets=('news',))
    blob.strip = True
    source = _source({'AAPL': []})
    result = _run(tmp_path / 'second', blob, {'news': source}, ['AAPL'],
                  NOW + timedelta(days=1), datasets=('news',))
    assert result.status == 'read_error'
    assert source.calls == []


@pytest.mark.parametrize('missing', ['FINNHUB_API_KEY', 'EDGAR_USER_AGENT'])
@pytest.mark.parametrize('check_only', [True, False])
def test_drill_requires_each_requested_source(monkeypatch, capsys, missing, check_only):
    module = _load('final_drill', ROOT / 'scripts/refresh_events.py')
    for key in ['EVENTS_DRILL_BLOB_READ_WRITE_TOKEN', 'FINNHUB_API_KEY', 'EDGAR_USER_AGENT']:
        monkeypatch.setenv(key, 'test-value')
    monkeypatch.setenv('EVENTS_BLOB_PREFIX', 'lens-events-drill')
    monkeypatch.delenv(missing)
    def forbidden(*args, **kwargs):
        pytest.fail('must fail before constructing clients or fetching')
    monkeypatch.setattr(module, 'open_durable', forbidden)
    monkeypatch.setattr(module, 'FinnhubEventSource', forbidden)
    monkeypatch.setattr(module, 'EdgarRecentIndex', forbidden)
    args = ['--drill', '--dataset', 'all'] + (['--check-config'] if check_only else [])
    assert module.main(args) == 2
    assert 'config_error=drill_sources_missing' in capsys.readouterr().out


@pytest.mark.parametrize('prefix', ['lens-events', '', 'invalid/prefix'])
def test_drill_rejects_any_non_drill_namespace(monkeypatch, capsys, prefix):
    module = _load('final_drill_prefix', ROOT / 'scripts/refresh_events.py')
    monkeypatch.setenv('EVENTS_DRILL_BLOB_READ_WRITE_TOKEN', 'test-value')
    monkeypatch.setenv('EVENTS_BLOB_PREFIX', prefix)
    assert module.main(['--drill', '--check-config']) == 2
    assert 'config_error=drill_prefix_invalid' in capsys.readouterr().out


def test_partial_ticker_refresh_does_not_shrink_monitor_universe(tmp_path):
    blob = MemoryBlob()
    source = _source({'AAPL': [], 'JPM': [], 'NVDA': []})
    _run(tmp_path / 'all', blob, {'news': source}, ['AAPL', 'JPM', 'NVDA'],
         NOW, datasets=('news',))
    _run(tmp_path / 'one', blob, {'news': source}, ['AAPL'],
         NOW + timedelta(days=1), datasets=('news',))
    assert pull_checkpoint(blob)[0]['expected_tickers'] == ['AAPL', 'JPM', 'NVDA']


def test_invalid_item_cannot_advance_success_watermark(tmp_path):
    blob = MemoryBlob()
    _run(tmp_path / 'first', blob, {'news': _source({'AAPL': [_row('AAPL', 1)]})},
         ['AAPL'], NOW, datasets=('news',))
    before = pull_checkpoint(blob)[0]['datasets']['news']['states']['AAPL']
    bad = _source({'AAPL': [{'headline': 'missing source and date'}]})
    result = _run(tmp_path / 'bad', blob, {'news': bad}, ['AAPL'],
                  NOW + timedelta(days=1), datasets=('news',))
    after = pull_checkpoint(blob)[0]['datasets']['news']['states']['AAPL']
    assert result.reports[0].outcomes[0].error_class == 'invalid_payload'
    assert after['coverage_through'] == before['coverage_through']
    assert after['last_successful_check_at'] == before['last_successful_check_at']
    assert after['status'] == 'stale'


def test_provider_lookback_gap_survives_later_success(tmp_path):
    blob = MemoryBlob()
    source = _source({'AAPL': []})
    source.lookback_floor = lambda now: now - timedelta(days=1)
    _run(tmp_path / 'first', blob, {'news': source}, ['AAPL'], NOW, datasets=('news',))
    before = pull_checkpoint(blob)[0]['datasets']['news']['states']['AAPL']
    assert before['coverage_gaps']
    _run(tmp_path / 'second', blob, {'news': source}, ['AAPL'],
         NOW + timedelta(hours=3), datasets=('news',))
    after = pull_checkpoint(blob)[0]['datasets']['news']['states']['AAPL']
    for gap in before['coverage_gaps']:
        assert gap in after['coverage_gaps']
    assert after['status'] == 'partial'


@pytest.mark.parametrize('payload', [{}, {'error': 'temporarily unavailable'},
                                      {'filings': {'recent': {'form': ['10-Q']}}}])
def test_sec_bad_success_body_is_not_zero_filings(payload):
    from company_lens.events.providers import EdgarRecentIndex

    class Response:
        status_code = 200
        headers: ClassVar[dict] = {}

        def json(self):
            return payload

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    result = EdgarRecentIndex('test test@example.com', ciks={'AAPL': 320193},
                              session=Session()).fetch('AAPL', NOW - timedelta(days=1), NOW)
    assert not result.ok
    assert result.error_class == 'invalid_payload'


def test_mutable_blob_objects_have_bounded_cache_and_body_etag():
    from company_lens.events.blob_store import HttpBlobTransport

    calls = []

    class Response:
        status_code = 200
        headers: ClassVar[dict] = {'etag': 'body-etag'}
        content = b'{}'

        def json(self):
            return {'url': 'https://example.com/blob'}

    class Session:
        def put(self, url, **kwargs):
            calls.append(kwargs)
            return Response()

        def get(self, url, **kwargs):
            calls.append(kwargs)
            return Response()

    transport = HttpBlobTransport('test-only', session=Session())
    transport.put(commit_path(), b'{}', if_match='old-etag', overwrite=True)
    assert calls[0]['headers']['x-if-match'] == 'old-etag'
    assert calls[0]['headers']['x-cache-control-max-age'] == '60'
    assert transport.read_url('https://example.com/blob') == (b'{}', 'body-etag')
    assert calls[1]['headers']['Cache-Control'] == 'no-cache'
