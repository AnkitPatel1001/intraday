"""Indian-adapted Time Machine.

Replays a planned NSE day trade before risking money: N simulated runs of the
rest of the session from the entry, plus the same rule on every past session.

Adapted from trader-timemachine (day-trader-skill, MIT, Jake Schincariol)
for NSE microstructure: 09:15–15:30 IST, 75 five-minute bars, Asia/Kolkata,
NSE holidays. Algorithm (ratio-pool Monte Carlo, stop-first-in-bar) unchanged.

SIMULATION, NOT PREDICTION. Same seed + same data = same numbers.
"""

from __future__ import annotations

import datetime
import math
import random
import statistics

from app.core.calendar import (
    OPEN_MIN, CLOSE_MIN, SESSION_BARS, BAR_MIN, is_trading_day,
)
from app.core.primitives import BarSeries, Candle
from app.core.timezone import IST

MIN_SESSIONS = 20
SAMPLE_PATHS = 160
BAND_PATHS = 2000
BAND_Q = (0.05, 0.25, 0.5, 0.75, 0.95)
HIST_BINS = 24
COIN_FLIP = 0.05
STRONG = 0.15
MANY_NEITHER = 0.40
DEFAULT_SEED = 19


class TimeMachineError(Exception):
    pass


# ---------------------------------------------------------------- pool

def split_sessions(candles: list[Candle]) -> dict[str, dict[int, Candle]]:
    """{date_iso: {slot: candle}} from 5-min IST candles."""
    days: dict[str, dict[int, Candle]] = {}
    for c in candles:
        t = c.ts.astimezone(IST)
        mins = t.hour * 60 + t.minute
        if mins < OPEN_MIN or mins >= CLOSE_MIN:
            continue
        if t.minute % BAR_MIN:
            continue
        slot = (mins - OPEN_MIN) // BAR_MIN
        days.setdefault(t.date().isoformat(), {})[slot] = c
    return days


def full_sessions(
    days: dict[str, dict[int, Candle]], before: str,
) -> tuple[list[tuple[str, list[Candle]]], list[dict]]:
    """Full sessions (all 75 bars) strictly before `before` date."""
    full, short = [], []
    for d in sorted(days):
        if d >= before:
            continue
        s = days[d]
        if len(s) == SESSION_BARS:
            full.append((d, [s[i] for i in range(SESSION_BARS)]))
        else:
            short.append({"date": d, "bars": len(s)})
    return full, short


def build_pool(sessions: list[tuple[str, list[Candle]]]) -> list[list[tuple[float, float, float, float]]]:
    """pool[slot] = each past session's bar as (o,h,l,c)/prev_close ratios."""
    pool: list[list[tuple[float, float, float, float]]] = [[] for _ in range(SESSION_BARS)]
    for _, bars in sessions:
        for i in range(1, SESSION_BARS):
            pc = bars[i - 1].close
            if pc <= 0:
                continue
            pool[i].append((
                bars[i].open / pc, bars[i].high / pc,
                bars[i].low / pc, bars[i].close / pc,
            ))
    return pool


# ---------------------------------------------------------------- simulation

def _pct(a: list[float], q: float) -> float:
    return a[min(len(a) - 1, int(q * len(a)))]


def simulate(
    pool: list[list[tuple[float, float, float, float]]],
    entry: float, stop: float, target: float,
    k: int, last: int,
    replays: int = 10000, seed: int = DEFAULT_SEED, window: int = 2,
    side: str = "buy",
) -> dict:
    """Monte Carlo replays of bars k+1..last. Stop checked before target."""
    long = side == "buy"
    risk = (entry - stop) if long else (stop - entry)
    if risk <= 0:
        raise TimeMachineError("risk must be positive")
    r_target = round(((target - entry) if long else (entry - target)) / risk, 4)

    def pick_slot(rng: random.Random, i: int) -> int:
        if window == 0:
            return i
        return min(SESSION_BARS - 1, max(1, i + rng.randint(-window, window)))

    rng = random.Random(seed)
    choice = rng.choice
    outcomes: list[str] = []
    closes: list[float] = []
    paths: list[list[float]] = []
    Rs: list[float] = []

    for n in range(replays):
        p = entry
        outcome = None
        keep = n < SAMPLE_PATHS
        path = [entry]
        for i in range(k + 1, last + 1):
            slot_choices = pool[pick_slot(rng, i)]
            if not slot_choices:
                slot_choices = pool[i] if pool[i] else [(1, 1, 1, 1)]
            o_r, h_r, l_r, c_r = choice(slot_choices)
            hi, lo, cl = p * h_r, p * l_r, p * c_r
            if outcome is None:
                if long:
                    if lo <= stop:
                        outcome = "stop"
                    elif hi >= target:
                        outcome = "target"
                else:
                    if hi >= stop:
                        outcome = "stop"
                    elif lo <= target:
                        outcome = "target"
            p = cl
            if keep:
                path.append(round(p, 2))
        final_outcome = outcome or "close"
        outcomes.append(final_outcome)
        closes.append(p)
        if keep:
            paths.append(path)
        r = (r_target if final_outcome == "target"
             else -1.0 if final_outcome == "stop"
             else ((p - entry) if long else (entry - p)) / risk)
        Rs.append(r)

    cnt = {x: outcomes.count(x) for x in ("target", "stop", "close")}
    green = sum(
        1 for o, p in zip(outcomes, closes)
        if o == "target" or (o == "close" and (p > entry if long else p < entry))
    )
    srt = sorted(closes)

    # Fan-chart bands: second run with same seed, BAND_PATHS paths
    rng2 = random.Random(seed)
    choice2 = rng2.choice
    all_paths: list[list[float]] = []
    for _ in range(BAND_PATHS):
        p = entry
        path = [entry]
        for i in range(k + 1, last + 1):
            slot_choices = pool[pick_slot(rng2, i)]
            if not slot_choices:
                slot_choices = [(1, 1, 1, 1)]
            _, _, _, c_r = choice2(slot_choices)
            p = p * c_r
            path.append(p)
        all_paths.append(path)
    bands = []
    for j in range(last - k + 1):
        col = sorted(pp[j] for pp in all_paths)
        bands.append([round(_pct(col, q), 2) for q in BAND_Q])

    lo_, hi_ = _pct(srt, 0.01), _pct(srt, 0.99)
    w = (hi_ - lo_) / HIST_BINS if hi_ > lo_ else 1.0
    bins = [0] * HIST_BINS
    for c in srt:
        b = int((c - lo_) / w) if w > 0 else 0
        if 0 <= b < HIST_BINS:
            bins[b] += 1

    return {
        "replays": replays, "seed": seed, "window": window,
        "bars_left": last - k,
        "p_target": round(cnt["target"] / replays, 4),
        "p_stop": round(cnt["stop"] / replays, 4),
        "p_neither": round(cnt["close"] / replays, 4),
        "p_green": round(green / replays, 4),
        "median_close": round(_pct(srt, 0.5), 2),
        "p5_close": round(_pct(srt, 0.05), 2),
        "p95_close": round(_pct(srt, 0.95), 2),
        "avg_R": round(statistics.mean(Rs), 3),
        "r_at_target": r_target,
        "band_paths": BAND_PATHS,
        "bands": bands,
        "sample_paths": paths,
        "hist": {"lo": round(lo_, 2), "hi": round(hi_, 2), "bins": bins},
    }


# ---------------------------------------------------------------- history

def _cents_away(x: float, long: bool) -> float:
    c = round(x * 100, 4)
    return (math.floor(c) if long else math.ceil(c)) / 100.0


def _opening_range(bars: list[Candle], n: int) -> tuple[float, float]:
    return max(b.high for b in bars[:n]), min(b.low for b in bars[:n])


def _rule_stop(rule: dict, oh: float, ol: float, entry: float, long: bool) -> float:
    r = rule["stop_rule"]
    if r == "or_mid":
        return _cents_away((oh + ol) / 2, long)
    if r in ("or_low", "or_high"):
        return _cents_away(ol if long else oh, long)
    frac = rule.get("stop_pct", 1.0) / 100.0
    return _cents_away(entry * (1 - frac) if long else entry * (1 + frac), long)


def history_replay(
    sessions: list[tuple[str, list[Candle]]],
    rule: dict, last: int, side: str = "buy",
) -> dict:
    """The plan's rule on every past full session."""
    long = side == "buy"
    n = rule["or_minutes"] // BAR_MIN
    trades = []
    for d, bars in sessions:
        oh, ol = _opening_range(bars, n)
        kk = next(
            (i for i in range(n, last + 1)
             if (bars[i].close > oh if long else bars[i].close < ol)),
            None,
        )
        if kk is None:
            continue
        e = round(bars[kk].close, 2)
        s = _rule_stop(rule, oh, ol, e, long)
        risk = (e - s) if long else (s - e)
        if risk <= 0:
            continue
        t = round(e + rule["target_r"] * risk, 2) if long else round(e - rule["target_r"] * risk, 2)
        oc = None
        for b in bars[kk + 1 : last + 1]:
            if (b.low <= s) if long else (b.high >= s):
                oc = "stop"
                break
            if (b.high >= t) if long else (b.low <= t):
                oc = "target"
                break
        cl = bars[last].close
        R = ((t - e) if long else (e - t)) / risk if oc == "target" else (
            -1.0 if oc == "stop" else ((cl - e) if long else (e - cl)) / risk
        )
        trades.append({
            "date": d, "entry": e, "stop": s, "target": t,
            "outcome": oc or "close", "R": round(R, 2),
        })
    return {
        "sessions": len(sessions),
        "triggered": len(trades),
        "target": sum(1 for x in trades if x["outcome"] == "target"),
        "stop": sum(1 for x in trades if x["outcome"] == "stop"),
        "close": sum(1 for x in trades if x["outcome"] == "close"),
        "green": sum(1 for x in trades if x["R"] > 0),
        "avg_R": round(statistics.mean(x["R"] for x in trades), 3) if trades else None,
        "rule": rule,
        "trades": trades,
    }


# ---------------------------------------------------------------- verdict

def lean(mc: dict) -> tuple[float, float, float] | None:
    pt, ps = mc["p_target"], mc["p_stop"]
    if pt + ps <= 0:
        return None
    r = mc.get("r_at_target") or 1.0
    share, even = pt / (pt + ps), 1.0 / (1.0 + r)
    return share - even, share, even


def verdict(mc: dict) -> str:
    lv = lean(mc)
    if lv is None:
        return "No replay reached the target or the stop: the final price decides every one."
    d, share, even = lv
    r = mc.get("r_at_target") or 1.0
    pt, ps = mc["p_target"], mc["p_stop"]
    one_r = abs(r - 1.0) < 0.005
    if abs(d) < COIN_FLIP:
        head = "Close to a coin flip" if one_r else "Close to break-even"
    elif abs(d) < STRONG:
        head = "Leans toward the target" if d > 0 else "Leans toward the stop"
    else:
        head = "Strongly toward the target" if d > 0 else "Strongly toward the stop"
    odds = f"target first {100*pt:.1f}% vs stop first {100*ps:.1f}%"
    if one_r:
        return f"{head}: {odds}."
    return (
        f"{head}: at {r:.2f}R the target needs {100*even:.0f}% of side-hits; "
        f"it got {100*share:.0f}% ({odds})."
    )


def verdict_notes(mc: dict) -> list[str]:
    notes = []
    pn = mc.get("p_neither", 0)
    lv = lean(mc)
    if pn > MANY_NEITHER and lv is not None:
        notes.append(f"{100*pn:.1f}% of replays hit neither by the end; the final price decides those.")
    avg = mc.get("avg_R")
    if lv and abs(lv[0]) >= COIN_FLIP and avg is not None and avg != 0 and (avg > 0) != (lv[0] > 0):
        notes.append(f"Average R is {avg:+.3f} all the same: neither-hitters pull it the other way.")
    return notes


# ---------------------------------------------------------------- plan + run

def normalize_plan(raw: dict) -> dict:
    sym = str(raw.get("symbol") or "").strip().upper()
    if not sym or len(sym) > 20:
        raise TimeMachineError(f"bad symbol: {raw.get('symbol')!r}")
    side = str(raw.get("side") or "buy").lower()
    if side not in ("buy", "sell"):
        raise TimeMachineError(f"side must be buy or sell, got {raw.get('side')!r}")
    try:
        date = datetime.date.fromisoformat(str(raw.get("date") or "")).isoformat()
    except ValueError:
        raise TimeMachineError(f"date must be YYYY-MM-DD, got {raw.get('date')!r}")
    entry = float(raw["entry"])
    stop = float(raw["stop"])
    target = float(raw["target"])
    long = side == "buy"
    if long and not (stop < entry < target):
        raise TimeMachineError(f"buy needs stop < entry < target (got {stop}, {entry}, {target})")
    if not long and not (target < entry < stop):
        raise TimeMachineError(f"sell needs target < entry < stop (got {target}, {entry}, {stop})")
    k = int(raw.get("entry_bar", 0))
    if not 0 <= k <= SESSION_BARS - 2:
        raise TimeMachineError(f"entry_bar must be 0..{SESSION_BARS-2}, got {k}")
    or_min = int((raw.get("opening_range") or {}).get("minutes", 15))
    if or_min < BAR_MIN or or_min % BAR_MIN or or_min >= 390:
        raise TimeMachineError(f"opening_range.minutes must be multiple of 5, got {or_min}")
    risk = (entry - stop) if long else (stop - entry)
    return {
        "symbol": sym, "side": side, "date": date,
        "setup": str(raw.get("setup") or "orb"),
        "entry": entry, "entry_bar": k, "stop": stop, "target": target,
        "risk_per_share": round(risk, 2),
        "target_r": round(((target - entry) if long else (entry - target)) / risk, 2),
        "opening_range": {"minutes": or_min},
        "stop_rule": str(raw.get("stop_rule") or "auto"),
        "flat_by": raw.get("flat_by"),
    }


def run_time_machine(
    series: BarSeries,
    plan: dict,
    replays: int = 10000,
    seed: int = DEFAULT_SEED,
    window: int = 2,
    until_slot: int | None = None,
) -> dict:
    """Full time-machine run. series = 5-min bars. plan = normalized plan dict."""
    if series.interval != "5m":
        raise TimeMachineError(f"needs 5-min bars, got {series.interval}")
    if replays < 1 or replays > 1_000_000:
        raise TimeMachineError("replays must be 1..1000000")
    if not 0 <= window <= 10:
        raise TimeMachineError("window must be 0..10")

    days = split_sessions(series.candles)
    entry_day = days.get(plan["date"], {})
    k = plan["entry_bar"]
    if k not in entry_day:
        raise TimeMachineError(
            f"entry bar {k} not found for {plan['date']} — no complete 5-min bar"
        )
    last = until_slot if until_slot is not None else SESSION_BARS - 1
    if last <= k:
        raise TimeMachineError("nothing to replay after the entry bar")

    sessions, short = full_sessions(days, plan["date"])
    if len(sessions) < MIN_SESSIONS:
        raise TimeMachineError(
            f"only {len(sessions)} full session(s) before {plan['date']}; "
            f"need at least {MIN_SESSIONS}"
        )
    pool = build_pool(sessions)
    mc = simulate(pool, plan["entry"], plan["stop"], plan["target"], k, last,
                  replays, seed, window, plan["side"])
    mc = dict(mc, pool_sessions=len(sessions), pool_from=sessions[0][0], pool_to=sessions[-1][0])

    # History: ORB rule replay
    long = plan["side"] == "buy"
    n = plan["opening_range"]["minutes"] // BAR_MIN
    stop_rule = plan["stop_rule"]
    if stop_rule == "auto":
        stop_rule = "or_mid" if long else "or_high"
    rule = {
        "setup": "orb",
        "or_minutes": plan["opening_range"]["minutes"],
        "stop_rule": stop_rule,
        "target_r": plan["target_r"],
        "stop_pct": round(100.0 * plan["risk_per_share"] / plan["entry"], 4),
    }
    history = history_replay(sessions, rule, last, plan["side"])

    return {
        "created_by": "indian-market-intel/time-machine",
        "note": (
            f"Simulation from {plan['symbol']}'s own last {len(sessions)} full NSE sessions. "
            "Not a prediction. Earnings, news, and halts can exceed historical patterns. "
            f"Reproducible with seed {seed}."
        ),
        "plan": plan,
        "mc": mc,
        "history": history,
        "verdict": verdict(mc),
        "verdict_notes": verdict_notes(mc),
        "data": {
            "sessions_left_out": short,
            "pool_sessions": len(sessions),
        },
    }
