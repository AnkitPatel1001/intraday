"""Technical indicators. Pure functions on list[float]. Tested against known fixtures."""

from __future__ import annotations

import math


def sma(values: list[float], n: int) -> list[float | None]:
    """Simple moving average. None for first n-1 bars."""
    if n <= 0:
        raise ValueError("n must be positive")
    out: list[float | None] = [None] * len(values)
    if len(values) < n:
        return out
    s = sum(values[:n])
    out[n - 1] = s / n
    for i in range(n, len(values)):
        s += values[i] - values[i - n]
        out[i] = s / n
    return out


def ema(values: list[float], n: int) -> list[float | None]:
    """Exponential moving average. First value = SMA of first n."""
    if n <= 0:
        raise ValueError("n must be positive")
    out: list[float | None] = [None] * len(values)
    if len(values) < n:
        return out
    k = 2.0 / (n + 1)
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(closes: list[float], n: int = 14) -> list[float | None]:
    """Wilder's RSI."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) < n + 1:
        return out
    gains = [max(0.0, closes[i] - closes[i - 1]) for i in range(1, len(closes))]
    losses = [max(0.0, closes[i - 1] - closes[i]) for i in range(1, len(closes))]
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
        out[i + 1] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """MACD line, signal line, histogram."""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line: list[float | None] = [
        (f - s) if f is not None and s is not None else None
        for f, s in zip(ema_fast, ema_slow)
    ]
    # signal = EMA of macd_line (skip leading None)
    valid = [(i, v) for i, v in enumerate(macd_line) if v is not None]
    sig: list[float | None] = [None] * len(closes)
    if len(valid) >= signal:
        vals = [v for _, v in valid]
        ema_sig = ema(vals, signal)
        for (idx, _), sv in zip(valid, ema_sig):
            sig[idx] = sv
    hist: list[float | None] = [
        (m - s) if m is not None and s is not None else None
        for m, s in zip(macd_line, sig)
    ]
    return macd_line, sig, hist


def atr(
    highs: list[float], lows: list[float], closes: list[float], n: int = 14,
) -> list[float | None]:
    """Average True Range (Wilder)."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) < n + 1:
        return out
    trs = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    prev = sum(trs[1 : n + 1]) / n
    out[n] = prev
    for i in range(n + 1, len(closes)):
        prev = (prev * (n - 1) + trs[i]) / n
        out[i] = prev
    return out


def vwap(
    highs: list[float], lows: list[float], closes: list[float],
    volumes: list[int],
) -> list[float]:
    """Session VWAP (cumulative typical-price * volume / volume)."""
    out = []
    cum_pv = 0.0
    cum_v = 0
    for h, l, c, v in zip(highs, lows, closes, volumes):
        tp = (h + l + c) / 3.0
        cum_pv += tp * v
        cum_v += v
        out.append(cum_pv / cum_v if cum_v > 0 else c)
    return out


def bollinger(
    closes: list[float], n: int = 20, k: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Bollinger bands: (upper, middle, lower)."""
    mid = sma(closes, n)
    upper: list[float | None] = [None] * len(closes)
    lower: list[float | None] = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        window = closes[i - n + 1 : i + 1]
        m = mid[i]
        if m is None:
            continue
        var = sum((x - m) ** 2 for x in window) / n
        sd = math.sqrt(var)
        upper[i] = m + k * sd
        lower[i] = m - k * sd
    return upper, mid, lower


def stochastic(
    highs: list[float], lows: list[float], closes: list[float],
    k_period: int = 14, d_period: int = 3,
) -> tuple[list[float | None], list[float | None]]:
    """Stochastic oscillator: (%K, %D)."""
    k_vals: list[float | None] = [None] * len(closes)
    for i in range(k_period - 1, len(closes)):
        hh = max(highs[i - k_period + 1 : i + 1])
        ll = min(lows[i - k_period + 1 : i + 1])
        k_vals[i] = 50.0 if hh == ll else (closes[i] - ll) / (hh - ll) * 100
    d_vals: list[float | None] = [None] * len(closes)
    for i in range(k_period + d_period - 2, len(closes)):
        window = k_vals[i - d_period + 1 : i + 1]
        if all(v is not None for v in window):
            d_vals[i] = sum(window) / d_period  # type: ignore
    return k_vals, d_vals
