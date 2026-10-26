"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { apiGet } from "@/lib/api";
import type { BarsResponse, Quote } from "@/lib/types";
import { formatINR, formatNumber, formatTime, formatVolume } from "@/lib/format";
import PriceChart from "@/components/PriceChart";
import FreshnessBadge from "@/components/FreshnessBadge";

const INTERVALS = ["1m", "5m", "15m", "1d"];
const DAY_OPTIONS = [7, 30, 90, 180];

interface IndicatorSet {
  rsi_14: number | null;
  sma20: number | null;
  sma50: number | null;
  ema9: number | null;
  ema21: number | null;
  atr_14: number | null;
  vwap: number | null;
}

function sma(values: number[], period: number): number | null {
  if (values.length < period) return null;
  const slice = values.slice(-period);
  return slice.reduce((a, b) => a + b, 0) / period;
}

function ema(values: number[], period: number): number | null {
  if (values.length < period) return null;
  const k = 2 / (period + 1);
  let prev = values.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < values.length; i++) {
    prev = values[i] * k + prev * (1 - k);
  }
  return prev;
}

function rsi(values: number[], period = 14): number | null {
  if (values.length < period + 1) return null;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const diff = values[i] - values[i - 1];
    if (diff >= 0) gain += diff;
    else loss -= diff;
  }
  let avgGain = gain / period;
  let avgLoss = loss / period;
  for (let i = period + 1; i < values.length; i++) {
    const diff = values[i] - values[i - 1];
    avgGain = (avgGain * (period - 1) + Math.max(diff, 0)) / period;
    avgLoss = (avgLoss * (period - 1) + Math.max(-diff, 0)) / period;
  }
  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

function atr(
  highs: number[],
  lows: number[],
  closes: number[],
  period = 14
): number | null {
  if (highs.length < period + 1) return null;
  const trs: number[] = [];
  for (let i = 1; i < highs.length; i++) {
    trs.push(
      Math.max(
        highs[i] - lows[i],
        Math.abs(highs[i] - closes[i - 1]),
        Math.abs(lows[i] - closes[i - 1])
      )
    );
  }
  if (trs.length < period) return null;
  let prev = trs.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < trs.length; i++) {
    prev = (prev * (period - 1) + trs[i]) / period;
  }
  return prev;
}

function vwap(
  highs: number[],
  lows: number[],
  closes: number[],
  volumes: number[]
): number | null {
  let pv = 0;
  let vol = 0;
  for (let i = 0; i < closes.length; i++) {
    const typical = (highs[i] + lows[i] + closes[i]) / 3;
    pv += typical * volumes[i];
    vol += volumes[i];
  }
  return vol > 0 ? pv / vol : null;
}

export default function ResearchPage() {
  const params = useParams<{ symbol: string }>();
  const router = useRouter();
  const symbol = useMemo(
    () => decodeURIComponent(params?.symbol ?? "RELIANCE").toUpperCase(),
    [params]
  );
  const [symInput, setSymInput] = useState("");
  const goSymbol = (raw: string) => {
    const s = raw.trim().toUpperCase().replace(/\.NS$|\.BO$/, "");
    if (s) router.push(`/research/${encodeURIComponent(s)}`);
  };

  const [interval, setInterval_] = useState("5m");
  const [days, setDays] = useState(30);

  const [bars, setBars] = useState<BarsResponse | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [b, q] = await Promise.all([
        apiGet<BarsResponse>(`/api/v1/market/bars/${encodeURIComponent(symbol)}`, {
          interval,
          days,
        }),
        apiGet<Quote>(`/api/v1/market/quote/${encodeURIComponent(symbol)}`).catch(
          () => null
        ),
      ]);
      setBars(b);
      setQuote(q);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBars(null);
      setQuote(null);
    } finally {
      setLoading(false);
    }
  }, [symbol, interval, days]);

  useEffect(() => {
    load();
  }, [load]);

  const candles = bars?.candles ?? [];

  const indicators: IndicatorSet = useMemo(() => {
    const closes = candles.map((c) => c.close);
    const highs = candles.map((c) => c.high);
    const lows = candles.map((c) => c.low);
    const volumes = candles.map((c) => c.volume);
    return {
      rsi_14: rsi(closes, 14),
      sma20: sma(closes, 20),
      sma50: sma(closes, 50),
      ema9: ema(closes, 9),
      ema21: ema(closes, 21),
      atr_14: atr(highs, lows, closes, 14),
      vwap: vwap(highs, lows, closes, volumes),
    };
  }, [candles]);

  const last = candles[candles.length - 1];
  const firstToday = useMemo(() => {
    if (!candles.length) return null;
    const lastDay = candles[candles.length - 1].ts.slice(0, 10);
    return candles.find((c) => c.ts.slice(0, 10) === lastDay) ?? null;
  }, [candles]);

  const sessionHigh = firstToday
    ? Math.max(
        ...candles
          .filter((c) => c.ts.slice(0, 10) === firstToday.ts.slice(0, 10))
          .map((c) => c.high)
      )
    : null;
  const sessionLow = firstToday
    ? Math.min(
        ...candles
          .filter((c) => c.ts.slice(0, 10) === firstToday.ts.slice(0, 10))
          .map((c) => c.low)
      )
    : null;

  const changePct =
    firstToday && last && firstToday.open
      ? ((last.close - firstToday.open) / firstToday.open) * 100
      : null;

  const price = quote?.last_price ?? last?.close ?? null;

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold num text-white">{symbol}</h1>
            <span className="text-sm text-gray-500">research</span>
          </div>
          <p className="text-sm text-gray-500 mt-1">
            {bars
              ? `${bars.count} bars · ${bars.interval} · as of ${formatTime(
                  bars.as_of
                )}`
              : "loading price action…"}
          </p>
          <form
            className="flex items-center gap-2 mt-2"
            onSubmit={(e) => {
              e.preventDefault();
              goSymbol(symInput);
            }}
          >
            <input
              className="input-dark num w-40 py-1.5 text-xs"
              placeholder="e.g. TONBO, SILVERBEES"
              value={symInput}
              onChange={(e) => setSymInput(e.target.value)}
            />
            <button type="submit" className="btn-ghost text-xs">
              Go
            </button>
          </form>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {bars ? (
            <FreshnessBadge freshness={bars.freshness} source={bars.source} />
          ) : null}
          <Link href="/calculator" className="btn-ghost text-xs">
            Calculator
          </Link>
          <Link href="/timemachine" className="btn-ghost text-xs">
            Time Machine
          </Link>
          <Link href="/risk" className="btn-ghost text-xs">
            Risk check
          </Link>
        </div>
      </header>

      <div className="flex items-center gap-4 flex-wrap card px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="label-caps">Interval</span>
          <select
            className="input-dark num w-auto py-1.5"
            value={interval}
            onChange={(e) => setInterval_(e.target.value)}
          >
            {INTERVALS.map((iv) => (
              <option key={iv} value={iv}>
                {iv}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <span className="label-caps">Days</span>
          {DAY_OPTIONS.map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-2.5 py-1.5 text-xs num rounded border transition-colors ${
                days === d
                  ? "border-accent text-white bg-accent/15"
                  : "border-gray-800 text-gray-500 hover:border-gray-600"
              }`}
            >
              {d}
            </button>
          ))}
        </div>
        <button className="btn-ghost text-xs ml-auto" onClick={load} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {error ? (
        <div className="card p-5 border-red-500/40">
          <div className="text-red-400 font-semibold text-sm mb-1">
            Failed to load {symbol}
          </div>
          <div className="text-gray-400 text-sm num break-all">{error}</div>
          <button className="btn-primary mt-3" onClick={load}>
            Retry
          </button>
        </div>
      ) : null}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <section className="card p-4 xl:col-span-2">
          <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
            <div className="label-caps">Price action</div>
            <div className="text-xs num text-gray-500">
              {quote?.ts ? `quote ${formatTime(quote.ts)}` : ""}
            </div>
          </div>
          {loading ? (
            <div className="h-[420px] flex items-center justify-center text-sm text-gray-500">
              Loading candles…
            </div>
          ) : (
            <PriceChart candles={candles} interval={interval} height={420} />
          )}
        </section>

        <section className="space-y-6">
          <div className="card p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="label-caps">Quote</div>
              {quote ? (
                <FreshnessBadge freshness={quote.freshness} source={quote.source} />
              ) : null}
            </div>
            <div className="num text-3xl text-white">
              {price !== null ? formatINR(price) : "—"}
            </div>
            <div
              className={`num text-sm mt-1 ${
                changePct === null
                  ? "text-gray-500"
                  : changePct >= 0
                  ? "text-green"
                  : "text-red"
              }`}
            >
              {changePct === null
                ? "session change unavailable"
                : `${changePct >= 0 ? "+" : ""}${changePct.toFixed(2)}% from open`}
            </div>

            <div className="grid grid-cols-2 gap-3 mt-4 text-sm">
              <MiniField k="Volume" v={formatVolume(quote?.volume ?? last?.volume)} />
              <MiniField
                k="Bar close"
                v={last ? formatINR(last.close) : "—"}
              />
              <MiniField k="Session high" v={sessionHigh ? formatINR(sessionHigh) : "—"} />
              <MiniField k="Session low" v={sessionLow ? formatINR(sessionLow) : "—"} />
              <MiniField k="Source" v={quote?.source ?? bars?.source ?? "—"} />
              <MiniField
                k="Exchange"
                v={quote?.exchange ?? bars?.exchange ?? "NSE"}
              />
            </div>
          </div>

          <div className="card p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="label-caps">Indicators</div>
              <span className="text-[11px] text-gray-600">
                computed from {candles.length} bars
              </span>
            </div>
            <div className="space-y-2 text-sm">
              <IndRow
                name="RSI(14)"
                value={indicators.rsi_14}
                hint={
                  indicators.rsi_14 === null
                    ? "—"
                    : indicators.rsi_14 < 30
                    ? "oversold"
                    : indicators.rsi_14 > 70
                    ? "overbought"
                    : "neutral"
                }
                tone={
                  indicators.rsi_14 !== null && indicators.rsi_14 < 30
                    ? "green"
                    : indicators.rsi_14 !== null && indicators.rsi_14 > 70
                    ? "red"
                    : undefined
                }
              />
              <IndRow name="SMA(20)" value={indicators.sma20} />
              <IndRow name="SMA(50)" value={indicators.sma50} />
              <IndRow name="EMA(9)" value={indicators.ema9} />
              <IndRow name="EMA(21)" value={indicators.ema21} />
              <IndRow
                name="ATR(14)"
                value={indicators.atr_14}
                hint={
                  indicators.atr_14 !== null && price
                    ? `${((indicators.atr_14 / price) * 100).toFixed(2)}% of price`
                    : undefined
                }
              />
              <IndRow name="VWAP" value={indicators.vwap} />
            </div>

            <div className="mt-4 border-t border-gray-800 pt-3 text-[11px] text-gray-600 leading-relaxed">
              Values computed client-side from returned OHLCV. Bars label:{" "}
              {bars?.staleness !== undefined && bars?.staleness !== null
                ? `staleness ${formatNumber(
                    typeof bars.staleness === "number"
                      ? bars.staleness
                      : Number(bars.staleness),
                    2
                  )}`
                : "—"}
              {" · "}
              {bars?.freshness ?? "unknown"} data.
            </div>
          </div>
        </section>
      </div>

      <section className="card p-5">
        <div className="label-caps mb-3">Next steps</div>
        <div className="flex gap-3 flex-wrap text-sm">
          <Link
            href={`/research/${encodeURIComponent(symbol)}`}
            className="btn-ghost text-xs"
            onClick={() => undefined}
          >
            Reload this symbol
          </Link>
          <Link href="/scanner" className="btn-ghost text-xs">
            Scan for setups
          </Link>
          <Link href="/backtest" className="btn-ghost text-xs">
            Backtest {symbol}
          </Link>
          <Link href="/paper" className="btn-ghost text-xs">
            Paper trade {symbol}
          </Link>
        </div>
        <p className="text-[11px] text-gray-600 mt-3">
          Research view only. Freshness labels above describe the feed behind
          these numbers — treat synthetic/simulated feeds accordingly.
        </p>
      </section>
    </div>
  );
}

function MiniField({ k, v }: { k: string; v: string }) {
  return (
    <div className="bg-[#0d1321] border border-gray-800 rounded p-2.5">
      <div className="label-caps">{k}</div>
      <div className="num text-gray-200 mt-1">{v}</div>
    </div>
  );
}

function IndRow({
  name,
  value,
  hint,
  tone,
}: {
  name: string;
  value: number | null;
  hint?: string;
  tone?: "green" | "red";
}) {
  const cls =
    tone === "green" ? "text-green" : tone === "red" ? "text-red" : "text-gray-200";
  return (
    <div className="flex items-center justify-between gap-3 border-b border-gray-800/60 pb-1.5">
      <span className="text-gray-500">{name}</span>
      <span className="flex items-center gap-3">
        {hint ? <span className="text-[11px] text-gray-600">{hint}</span> : null}
        <span className={`num ${cls}`}>
          {value === null || Number.isNaN(value) ? "—" : formatNumber(value, 2)}
        </span>
      </span>
    </div>
  );
}
