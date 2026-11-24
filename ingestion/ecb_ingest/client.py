"""HTTP client for the ECB Data Portal SDMX REST API.

Facts verified against the live API (tests/fixtures/):
- `.../service/data/{flow}/{key}?format=csvdata&startPeriod=..&endPeriod=..&updatedAfter=..` returns CSV.
- When nothing matches (no observations updated after the timestamp, or an unknown key) the API answers
  HTTP 404 with an `application/problem+json` body, not an empty CSV. We surface that as `has_data=False`;
  callers decide whether "no data" is normal (incremental) or an error (first full load).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import quote, urlencode

import httpx
from tenacity import RetryCallState, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)

USER_AGENT = "ecb-markets-warehouse/0.1 (+python-httpx)"
_RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


class TransientApiError(Exception):
    """Retryable failure: network error, timeout, 429 or 5xx."""


class EcbApiError(Exception):
    """Non-retryable API failure (e.g. 400 bad query)."""


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int
    body: bytes  # exactly as received
    content_type: str
    has_data: bool
    detail: str = ""


def build_url(base_url: str, flow: str, key: str, params: dict[str, str | None]) -> str:
    """Build the request URL. The key goes into the path verbatim (`+` joins values and must not be
    percent-encoded); query values are percent-encoded (`+00:00` in a timestamp becomes `%2B00%3A00`)."""
    clean = {k: v for k, v in params.items() if v is not None}
    query = urlencode(clean, quote_via=quote, safe="")
    return f"{base_url.rstrip('/')}/data/{flow}/{key}?{query}"


def _log_retry(state: RetryCallState) -> None:
    exc = state.outcome.exception() if state.outcome else None
    log.warning("ECB request failed (attempt %s): %s; retrying", state.attempt_number, exc)


class EcbClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 120.0,
        transport: httpx.BaseTransport | None = None,
        max_attempts: int = 5,
        backoff_multiplier: float = 2.0,
        backoff_max: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=15.0),
            transport=transport,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
        self._retrying = retry(
            reraise=True,
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=backoff_multiplier, max=backoff_max),
            retry=retry_if_exception_type(TransientApiError),
            before_sleep=_log_retry,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> EcbClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch(
        self,
        flow: str,
        key: str,
        *,
        fmt: str = "csvdata",
        start_period: str | None = None,
        end_period: str | None = None,
        updated_after: str | None = None,
    ) -> FetchResult:
        url = build_url(
            self.base_url,
            flow,
            key,
            {"format": fmt, "startPeriod": start_period, "endPeriod": end_period, "updatedAfter": updated_after},
        )
        return self._retrying(self._get)(url)

    def _get(self, url: str) -> FetchResult:
        log.info("GET %s", url)
        try:
            resp = self._http.get(url)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise TransientApiError(f"{type(exc).__name__}: {exc}") from exc
        ctype = resp.headers.get("content-type", "")
        if resp.status_code in _RETRY_STATUS:
            raise TransientApiError(f"HTTP {resp.status_code} for {url}")
        if resp.status_code == 404:
            return FetchResult(url, 404, resp.content, ctype, has_data=False, detail=_problem_detail(resp))
        if resp.status_code != 200:
            raise EcbApiError(f"HTTP {resp.status_code} for {url}: {resp.text[:500]}")
        return FetchResult(url, 200, resp.content, ctype, has_data=bool(resp.content.strip()))


def _problem_detail(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("detail", ""))[:300]
    except ValueError:
        return resp.text[:300]
