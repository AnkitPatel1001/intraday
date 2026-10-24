"""Core primitives: Candle/Bar, OHLCV series, data labels."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DataFreshness(str, Enum):
    LIVE = "live"
    DELAYED = "delayed"
    HISTORICAL = "historical"
    SIMULATED = "simulated"
    SYNTHETIC = "synthetic"


@dataclass(frozen=True)
class Candle:
    """One OHLCV bar. ts is timezone-aware IST."""
    ts: datetime.datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    def validate(self) -> None:
        if self.high < self.low:
            raise ValueError(f"high {self.high} < low {self.low}")
        if self.high < max(self.open, self.close):
            raise ValueError(f"high {self.high} < max(o={self.open}, c={self.close})")
        if self.low > min(self.open, self.close):
            raise ValueError(f"low {self.low} > min(o={self.open}, c={self.close})")
        if self.volume < 0:
            raise ValueError(f"negative volume {self.volume}")


@dataclass
class BarSeries:
    """Ordered OHLCV bars for one symbol + interval."""
    symbol: str
    interval: str  # '1m','5m','15m','1d'
    exchange: str  # 'NSE','BSE'
    freshness: DataFreshness
    source: str    # 'demo','yahoo','kite', etc.
    as_of: datetime.datetime
    candles: list[Candle] = field(default_factory=list)

    @property
    def closes(self) -> list[float]:
        return [c.close for c in self.candles]

    @property
    def highs(self) -> list[float]:
        return [c.high for c in self.candles]

    @property
    def lows(self) -> list[float]:
        return [c.low for c in self.candles]

    @property
    def opens(self) -> list[float]:
        return [c.open for c in self.candles]

    @property
    def volumes(self) -> list[int]:
        return [c.volume for c in self.candles]

    def __len__(self) -> int:
        return len(self.candles)

    def label(self) -> str:
        return f"{self.freshness.value} ({self.source}) as of {self.as_of.isoformat()}"


@dataclass
class Quote:
    symbol: str
    exchange: str
    last_price: float
    volume: int
    ts: datetime.datetime
    freshness: DataFreshness
    source: str
