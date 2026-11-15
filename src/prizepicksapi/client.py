"""HTTP client for the prizepicksapi.com REST API (https://prizepicksapi.com/docs).

Standard library only. Every method maps to one documented endpoint and returns the decoded JSON body
(a dict with ``data`` and ``meta``), except ``export_csv`` which returns CSV text.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Dict, Iterator, Mapping, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .errors import APIError, RateLimitError, TransportError

__all__ = ["PrizePicksAPI", "DEFAULT_BASE_URL"]

DEFAULT_BASE_URL = "https://prizepicksapi.com"
USER_AGENT = "prizepicksapi-python/0.1.0"

# A transport takes (method, url, headers, timeout) and returns (status, headers, body_bytes).
Transport = Callable[[str, str, Dict[str, str], float], Tuple[int, Mapping[str, str], bytes]]


def _urllib_transport(method: str, url: str, headers: Dict[str, str], timeout: float):
    req = Request(url, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as res:
            return res.status, dict(res.headers.items()), res.read()
    except HTTPError as err:
        return err.code, dict(err.headers.items()) if err.headers else {}, err.read() or b""
    except URLError as err:
        raise TransportError(str(err.reason)) from err


def _clean(params: Mapping[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            out[key] = "true" if value else "false"
        elif isinstance(value, (list, tuple)):
            out[key] = ",".join(str(v) for v in value)
        else:
            out[key] = str(value)
    return out


class PrizePicksAPI:
    """Client for prizepicksapi.com.

    >>> api = PrizePicksAPI()                    # reads PRIZEPICKS_API_KEY from the environment
    >>> api.demo_projections(league="NBA", limit=2)["data"][0]["player"]["name"]

    ``user_request`` is sent as the optional X-User-Request header: one sentence describing the task,
    with no personal data. It never changes the data or the cost.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        user_request: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        transport: Optional[Transport] = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("PRIZEPICKS_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.user_request = user_request
        self.timeout = timeout
        self.max_retries = max_retries
        self._transport = transport or _urllib_transport
        self._sleep = sleep

    # ------------------------------------------------------------------ core
    def request(self, path: str, params: Optional[Mapping[str, Any]] = None, *, auth: bool = True, raw: bool = False) -> Any:
        """GET ``path`` with query ``params``. Retries 429 per-minute limits and 503s using Retry-After."""
        query = urlencode(_clean(params or {}))
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        headers = {"Accept": "text/csv" if raw else "application/json", "User-Agent": USER_AGENT}
        if auth:
            if not self.api_key:
                raise APIError(401, "INVALID_API_KEY", "Set PRIZEPICKS_API_KEY or pass api_key=. Free keys: https://prizepicksapi.com/sign-up. The demo_* methods need no key.")
            headers["Authorization"] = f"Bearer {self.api_key}"
            if self.user_request:
                headers["X-User-Request"] = quote(self.user_request, safe=" ,.;:!?()'-/")
        attempt = 0
        while True:
            status, resp_headers, body = self._transport("GET", url, headers, self.timeout)
            lower = {k.lower(): v for k, v in resp_headers.items()}
            if 200 <= status < 300 or status == 304:
                if raw:
                    return body.decode("utf-8")
                return json.loads(body.decode("utf-8")) if body else None
            error = self._error(status, lower, body)
            retryable = (isinstance(error, RateLimitError) and error.code != "MONTHLY_QUOTA_EXCEEDED") or status == 503
            if retryable and attempt < self.max_retries:
                attempt += 1
                self._sleep(min(error.retry_after or 2 ** attempt, 60))
                continue
            raise error

    @staticmethod
    def _error(status: int, headers: Mapping[str, str], body: bytes) -> APIError:
        code, message, payload = "HTTP_ERROR", f"HTTP {status}", None
        try:
            payload = json.loads(body.decode("utf-8"))
            err = payload.get("error", {}) if isinstance(payload, dict) else {}
            code = err.get("code", code)
            message = err.get("message", message)
        except (ValueError, UnicodeDecodeError):
            pass
        retry_after = None
        if headers.get("retry-after"):
            try:
                retry_after = float(headers["retry-after"])
            except ValueError:
                retry_after = None
        cls = RateLimitError if status == 429 else APIError
        return cls(status, code, message, retry_after=retry_after, body=payload)

    def paginate(self, path: str, params: Optional[Mapping[str, Any]] = None, *, auth: bool = True, max_pages: Optional[int] = None) -> Iterator[Dict[str, Any]]:
        """Yield every row across pages by following meta.next_cursor. Keep filters unchanged while paging."""
        params = dict(params or {})
        pages = 0
        while True:
            page = self.request(path, params, auth=auth)
            yield from page.get("data", [])
            pages += 1
            cursor = (page.get("meta") or {}).get("next_cursor")
            if not cursor or (max_pages is not None and pages >= max_pages):
                return
            params["cursor"] = cursor

    # ------------------------------------------------------------ keyless demo
    def demo_projections(self, **params: Any) -> Dict[str, Any]:
        """Fictional sample rows with the live schema. No key, no quota."""
        return self.request("/api/v1/demo/projections", params, auth=False)

    def demo_history(self, projection_id: str, **params: Any) -> Dict[str, Any]:
        return self.request(f"/api/v1/demo/projections/{quote(projection_id, safe='')}/history", params, auth=False)

    def demo_changes(self, **params: Any) -> Dict[str, Any]:
        return self.request("/api/v1/demo/changes", params, auth=False)

    def demo_payouts(self) -> Dict[str, Any]:
        return self.request("/api/v1/demo/payouts", auth=False)

    def demo_coverage(self) -> Dict[str, Any]:
        return self.request("/api/v1/demo/coverage", auth=False)

    def demo_export_csv(self, **params: Any) -> str:
        return self.request("/api/v1/demo/export", params, auth=False, raw=True)

    def credit_cost(self, path: str) -> Dict[str, Any]:
        """Quote the credit cost of a request path, for example '/api/v1/projections?league=NBA&limit=200'. No key."""
        return self.request("/api/v1/credit-costs", {"path": path}, auth=False)

    # ------------------------------------------------------------- live (key)
    def projections(self, **params: Any) -> Dict[str, Any]:
        """Current board. Filters: league, search, stat, tier, status, start_after, start_before, limit, cursor, view."""
        return self.request("/api/v1/projections", params)

    def iter_projections(self, *, max_pages: Optional[int] = None, **params: Any) -> Iterator[Dict[str, Any]]:
        return self.paginate("/api/v1/projections", params, max_pages=max_pages)

    def history(self, projection_id: str, **params: Any) -> Dict[str, Any]:
        """Every recorded change for one projection."""
        return self.request(f"/api/v1/projections/{quote(projection_id, safe='')}/history", params)

    def trending(self, **params: Any) -> Dict[str, Any]:
        return self.request("/api/v1/projections/trending", params)

    def changes(self, **params: Any) -> Dict[str, Any]:
        """Change feed: new, moved, pulled and restored lines. Resume with cursor."""
        return self.request("/api/v1/changes", params)

    def board(self, as_of: str, **params: Any) -> Dict[str, Any]:
        """The board as it stood at ``as_of`` (ISO 8601)."""
        return self.request("/api/v1/board", {"as_of": as_of, **params})

    def results(self, **params: Any) -> Dict[str, Any]:
        """Graded lines: line at game time, actual stat and over, under, push or void."""
        return self.request("/api/v1/results", params)

    def hit_rates(self, **params: Any) -> Dict[str, Any]:
        return self.request("/api/v1/hit-rates", params)

    def game_logs(self, **params: Any) -> Dict[str, Any]:
        return self.request("/api/v1/game-logs", params)

    def training_set(self, **params: Any) -> Dict[str, Any]:
        return self.request("/api/v1/training-set", params)

    def coverage(self) -> Dict[str, Any]:
        return self.request("/api/v1/coverage")

    def payouts(self) -> Dict[str, Any]:
        return self.request("/api/v1/payouts")

    def compare(self, **params: Any) -> Dict[str, Any]:
        """PrizePicks lines next to matched sportsbook and exchange quotes (NBA, NFL, NHL where matched)."""
        return self.request("/api/v1/compare", params)

    def players(self, **params: Any) -> Dict[str, Any]:
        return self.request("/api/v1/players", params)

    def fixtures(self, **params: Any) -> Dict[str, Any]:
        return self.request("/api/v1/fixtures", params)

    def export_csv(self, **params: Any) -> str:
        """One CSV page (up to 200 rows) of current projections with the same filters as projections()."""
        return self.request("/api/v1/export", params, raw=True)
