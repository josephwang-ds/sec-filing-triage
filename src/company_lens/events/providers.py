"""Live source adapters. Tokens stay in request headers and never in errors or URLs."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import requests

from company_lens.events.calendar import as_utc
from company_lens.events.refresh import FetchResult

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"


def _status_result(response: requests.Response) -> FetchResult | None:
    if response.status_code in {401, 403}:
        return FetchResult(ok=False, error_class="config", retryable=False)
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        try:
            delay = float(retry_after) if retry_after else None
        except ValueError:
            delay = None
        return FetchResult(ok=False, error_class="rate_limit", retryable=True, retry_after=delay)
    if response.status_code >= 500:
        return FetchResult(ok=False, error_class="upstream", retryable=True)
    if response.status_code >= 400:
        return FetchResult(ok=False, error_class="upstream", retryable=False)
    return None


class FinnhubEventSource:
    """Company news metadata. Article bodies are not downloaded."""

    name = "finnhub"
    max_window_days = 7

    def __init__(
        self,
        api_key: str,
        *,
        session: requests.Session | None = None,
        base_url: str = FINNHUB_BASE_URL,
        timeout: float = 20.0,
        lookback_days: int = 365,
    ) -> None:
        if not api_key.strip():
            raise ValueError("FINNHUB_API_KEY is required for a live news fetch")
        self._api_key = api_key.strip()
        self._session = session or requests.Session()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._lookback_days = lookback_days

    def lookback_floor(self, now: datetime) -> datetime | None:
        return as_utc(now) - timedelta(days=self._lookback_days)

    def fetch(self, ticker: str, start: datetime, end: datetime) -> FetchResult:
        try:
            response = self._session.get(
                f"{self._base_url}/company-news",
                params={
                    "from": as_utc(start).date().isoformat(),
                    "symbol": ticker,
                    "to": as_utc(end).date().isoformat(),
                },
                headers={"Accept": "application/json", "X-Finnhub-Token": self._api_key},
                timeout=self._timeout,
            )
        except requests.Timeout:
            return FetchResult(ok=False, error_class="timeout", retryable=True)
        except requests.RequestException:
            return FetchResult(ok=False, error_class="upstream", retryable=True)
        failed = _status_result(response)
        if failed is not None:
            return failed
        try:
            payload = response.json()
        except ValueError:
            return FetchResult(ok=False, error_class="upstream", retryable=True)
        if isinstance(payload, dict):
            return FetchResult(ok=False, error_class="upstream", retryable=True)
        if not isinstance(payload, list):
            return FetchResult(ok=False, error_class="upstream", retryable=False)
        items = [row for row in payload if isinstance(row, dict)]
        for item in items:
            item["source_kind"] = "news_provider"
            item["type"] = "news"
        return FetchResult(ok=True, items=items)


class EdgarRecentIndex:
    """Recent filing index only. This pass does not download documents."""

    name = "sec"
    max_window_days = 90

    def __init__(
        self,
        user_agent: str,
        *,
        ciks: dict[str, int],
        session: requests.Session | None = None,
        timeout: float = 20.0,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("EDGAR_USER_AGENT is required for a live SEC index fetch")
        self._user_agent = user_agent.strip()
        self._ciks = {ticker.upper(): cik for ticker, cik in ciks.items()}
        self._session = session or requests.Session()
        self._timeout = timeout

    def lookback_floor(self, now: datetime) -> datetime | None:
        return None

    def fetch(self, ticker: str, start: datetime, end: datetime) -> FetchResult:
        cik = self._ciks.get(ticker.upper())
        if cik is None:
            return FetchResult(ok=False, error_class="config", retryable=False)
        url = SEC_SUBMISSIONS.format(cik=cik)
        try:
            response = self._session.get(
                url,
                headers={"Accept": "application/json", "User-Agent": self._user_agent},
                timeout=self._timeout,
            )
        except requests.Timeout:
            return FetchResult(ok=False, error_class="timeout", retryable=True)
        except requests.RequestException:
            return FetchResult(ok=False, error_class="upstream", retryable=True)
        failed = _status_result(response)
        if failed is not None:
            return failed
        try:
            payload = response.json()
        except ValueError:
            return FetchResult(ok=False, error_class="upstream", retryable=True)
        return FetchResult(ok=True, items=_recent_filings(payload, ticker, cik, start, end))


def _recent_filings(
    payload: dict[str, Any], ticker: str, cik: int, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    recent = ((payload.get("filings") or {}).get("recent") or {})
    forms = recent.get("form") or []
    dates = recent.get("filingDate") or []
    accepted = recent.get("acceptanceDateTime") or []
    accessions = recent.get("accessionNumber") or []
    documents = recent.get("primaryDocument") or []
    start_day = as_utc(start).date()
    end_day = as_utc(end).date()
    items = []
    for index, form in enumerate(forms):
        filed = dates[index] if index < len(dates) else ""
        try:
            filed_day = datetime.fromisoformat(str(filed)).date()
        except ValueError:
            continue
        if filed_day < start_day or filed_day > end_day:
            continue
        accession = accessions[index] if index < len(accessions) else ""
        document = documents[index] if index < len(documents) else ""
        compact = str(accession).replace("-", "")
        if compact and document:
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{compact}/{document}"
        elif compact:
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{compact}/{accession}-index.html"
        else:
            url = "https://www.sec.gov/edgar/search/"
        items.append(
            {
                "accession": accession,
                "headline": f"{form} filed",
                "publisher": "SEC EDGAR",
                "significance_code": "sec_recent_filing",
                "source_kind": "sec",
                "source_url": url,
                "summary": f"Index entry for {ticker.upper()} {form}. The document body was not parsed.",
                "type": "filing",
                "acceptanceDateTime": accepted[index] if index < len(accepted) else filed,
            }
        )
    return items
