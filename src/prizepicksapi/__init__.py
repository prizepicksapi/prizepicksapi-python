"""Python client for prizepicksapi.com: live PrizePicks lines, goblin and demon tiers, line history and graded results.

Independent service operated by Stunning Couches LLC; not affiliated with PrizePicks.
"""

from .client import DEFAULT_BASE_URL, PrizePicksAPI
from .errors import APIError, PrizePicksAPIError, RateLimitError, TransportError

__version__ = "0.1.0"
__all__ = ["PrizePicksAPI", "DEFAULT_BASE_URL", "APIError", "PrizePicksAPIError", "RateLimitError", "TransportError", "__version__"]
