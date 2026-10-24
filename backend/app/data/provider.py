"""Provider-independent market data interface.

Every provider implements MarketDataProvider. Consumers never see provider
internals — they get BarSeries with explicit freshness + source labels.
"""

from __future__ import annotations

import abc
import datetime
from typing import Optional

from app.core.primitives import BarSeries, Quote, DataFreshness


class DataError(Exception):
    pass


class RateLimitError(DataError):
    pass


class AuthError(DataError):
    pass


class MarketDataProvider(abc.ABC):
    """Abstract market data provider for NSE/BSE."""

    name: str = "base"

    @abc.abstractmethod
    async def get_bars(
        self,
        symbol: str,
        interval: str,
        start: datetime.date,
        end: datetime.date,
    ) -> BarSeries:
        """Fetch OHLCV bars. interval: '1m','5m','15m','1d'."""

    @abc.abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        """Latest quote for a symbol."""

    @abc.abstractmethod
    async def get_batch_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Latest quotes for multiple symbols."""

    async def health(self) -> dict:
        return {"provider": self.name, "healthy": True}
