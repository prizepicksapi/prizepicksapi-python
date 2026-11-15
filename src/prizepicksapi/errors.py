from __future__ import annotations

from typing import Any, Optional


class PrizePicksAPIError(Exception):
    """Base class for every error raised by this package."""


class TransportError(PrizePicksAPIError):
    """The request never got an HTTP response (DNS, TLS, timeout)."""


class APIError(PrizePicksAPIError):
    """A non-2xx response. ``code`` is the API's stable error code, for example INVALID_API_KEY."""

    def __init__(self, status: int, code: str, message: str, *, retry_after: Optional[float] = None, body: Any = None) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.retry_after = retry_after
        self.body = body


class RateLimitError(APIError):
    """HTTP 429. Per-minute limits are retried automatically; a monthly quota is not."""
