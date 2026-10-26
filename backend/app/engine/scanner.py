"""Indian stock scanner. Trend, momentum, breakout, volume. Explains every match."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

from app.core.primitives import BarSeries, DataFreshness
from app.engine.indicators import sma, ema, rsi, macd, atr, vwap, bollinger


@dataclass
class ScanResult:
    symbol: str
    price: float
    setups: list[str]
    indicators: dict
    reason: str
    freshness: str
    source: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class ScanFilters:
    min_price: float = 10.0
    min_volume: int = 10000
    min_atr_pct: float = 0.5   # minimum ATR as % of price
    setups: list[str] = field(default_factory=lambda: ["orb", "breakout_20d", "rsi_oversold", "rsi_overbought", "ma_cross", "volume_spike"])


def scan_symbol(series: BarSeries, filters: ScanFilters) -> Optional[ScanResult]:
    """Scan one symbol. Returns None if filtered out."""
    candles = series.candles
    if len(candles) < 30:
        return None

    closes = series.closes
    highs = series.highs
    lows = series.lows
    volumes = series.volumes
    price = closes[-1]

    if price < filters.min_price:
        return None

    avg_vol = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else sum(volumes) / len(volumes)
    if avg_vol < filters.min_volume:
        return None

    indicators: dict = {}
    setups: list[str] = []
    reasons: list[str] = []
    warnings: list[str] = []

    # RSI
    rsi_vals = rsi(closes, 14)
    current_rsi = rsi_vals[-1] if rsi_vals[-1] is not None else None
    if current_rsi is not None:
        indicators["rsi_14"] = round(current_rsi, 1)
        if current_rsi < 30:
            setups.append("rsi_oversold")
            reasons.append(f"RSI(14)={current_rsi:.1f} < 30 (oversold)")
        elif current_rsi > 70:
            setups.append("rsi_overbought")
            reasons.append(f"RSI(14)={current_rsi:.1f} > 70 (overbought)")

    # Moving averages
    sma20 = sma(closes, 20)
    sma50 = sma(closes, 50)
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    if sma20[-1] is not None:
        indicators["sma20"] = round(sma20[-1], 2)
    if sma50[-1] is not None:
        indicators["sma50"] = round(sma50[-1], 2)
    if ema9[-1] is not None and ema21[-1] is not None:
        indicators["ema9"] = round(ema9[-1], 2)
        indicators["ema21"] = round(ema21[-1], 2)
        # MA cross
        if (ema9[-2] is not None and ema21[-2] is not None):
            if ema9[-2] <= ema21[-2] and ema9[-1] > ema21[-1]:
                setups.append("ma_cross")
                reasons.append("EMA9 crossed above EMA21 (bullish cross)")
            elif ema9[-2] >= ema21[-2] and ema9[-1] < ema21[-1]:
                setups.append("ma_cross")
                reasons.append("EMA9 crossed below EMA21 (bearish cross)")

    # MACD
    macd_line, macd_sig, macd_hist = macd(closes)
    if macd_line[-1] is not None and macd_sig[-1] is not None:
        indicators["macd"] = round(macd_line[-1], 4)
        indicators["macd_signal"] = round(macd_sig[-1], 4)
        indicators["macd_hist"] = round(macd_hist[-1] or 0, 4)
        if macd_hist[-1] is not None and macd_hist[-2] is not None:
            if macd_hist[-2] <= 0 < macd_hist[-1]:
                setups.append("macd_bullish")
                reasons.append("MACD histogram turned positive")

    # ATR
    atr_vals = atr(highs, lows, closes, 14)
    if atr_vals[-1] is not None:
        atr_pct = 100 * atr_vals[-1] / price
        indicators["atr_14"] = round(atr_vals[-1], 2)
        indicators["atr_pct"] = round(atr_pct, 2)
        if atr_pct < filters.min_atr_pct:
            warnings.append(f"low volatility: ATR {atr_pct:.2f}% < {filters.min_atr_pct}%")

    # Volume spike
    if len(volumes) >= 20:
        avg20 = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else avg_vol
        if avg20 > 0 and volumes[-1] > 2 * avg20:
            setups.append("volume_spike")
            reasons.append(f"volume {volumes[-1]:,} > 2x 20-bar avg ({avg20:,.0f})")
            indicators["volume_ratio"] = round(volumes[-1] / avg20, 2)

    # 20-bar breakout (for daily; for intraday use last N bars)
    n_check = min(20, len(closes) - 1)
    if n_check >= 5:
        hi = max(closes[-n_check-1:-1])
        if price > hi:
            setups.append("breakout_20d")
            reasons.append(f"price {price:.2f} > {n_check}-bar high {hi:.2f}")

    # VWAP
    vwap_vals = vwap(highs, lows, closes, volumes)
    if vwap_vals:
        indicators["vwap"] = round(vwap_vals[-1], 2)
        if price > vwap_vals[-1]:
            indicators["above_vwap"] = True
        else:
            indicators["above_vwap"] = False

    # Bollinger
    bb_upper, bb_mid, bb_lower = bollinger(closes, 20)
    if bb_upper[-1] is not None:
        indicators["bb_upper"] = round(bb_upper[-1], 2)
        indicators["bb_lower"] = round(bb_lower[-1], 2)

    if not setups:
        return None

    return ScanResult(
        symbol=series.symbol,
        price=round(price, 2),
        setups=setups,
        indicators=indicators,
        reason="; ".join(reasons),
        freshness=series.freshness.value,
        source=series.source,
        warnings=warnings,
    )


def scan_universe(
    series_map: dict[str, BarSeries], filters: ScanFilters,
) -> list[ScanResult]:
    results = []
    for sym, series in series_map.items():
        r = scan_symbol(series, filters)
        if r:
            results.append(r)
    results.sort(key=lambda x: x.price, reverse=True)
    return results
