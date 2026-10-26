"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import type { BacktestRequest, BacktestResponse } from "@/lib/types";
import {
  formatINR,
  formatINRSigned,
  formatNumber,
  formatPct,
  formatTime,
} from "@/lib/format";
import FreshnessBadge from "@/components/FreshnessBadge";

const STRATEGIES = [{ value: "orb", label: "ORB — opening range breakout" }];
const INTERVALS = ["1m", "5m", "15m", "1d"];

export default function BacktestPage() {
  const [symbol, setSymbol] = useState("RELIANCE");
  const [strategy, setStrategy] = useState("orb");
  const [interval, setInterval_] = useState("5m");
  const [days, setDays] = useState("90");
  const [capital, setCapital] = useState("500000");
  const [riskPct, setRiskPct] = useState("1");

  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const body: BacktestRequest = {
        symbol: symbol.toUpperCase().trim(),
        strategy,
        interval,
        days: Number(days) || 90,
        capital: Number(capital) || 500000,
        risk_pct: Number(riskPct) || 1,
      };
      const res = await apiPost<BacktestResponse>("/api/v1/backtest/run", body);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">Backtest</h1>
          <p className="text-sm text-gray-500 mt-1">
            Simulate a strategy over historical bars. Past performance ≠ future
            results.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {result ? (
            <FreshnessBadge freshness="historical" source={result.symbol} />
          ) : null}
          <span className="px-2 py-1 text-[10px] font-bold tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded">
            SIMULATED DATA
          </span>
        </div>
      </header>

      <section className="card p-5">
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
          <div>
            <label className="label-caps block mb-1.5">Symbol</label>
            <input
              className="input-dark num uppercase"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
            />
          </div>
          <div>
            <label className="label-caps block mb-1.5">Strategy</label>
            <select
              className="input-dark"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
            >
              {STRATEGIES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label-caps block mb-1.5">Interval</label>
            <select
              className="input-dark num"
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
          <div>
            <label className="label-caps block mb-1.5">Days</label>
            <input
              type="number"
              min={5}
              max={365}
              className="input-dark num"
              value={days}
              onChange={(e) => setDays(e.target.value)}
            />
          </div>
          <div>
            <label className="label-caps block mb-1.5">Capital (₹)</label>
            <input
              type="number"
              className="input-dark num"
              value={capital}
              onChange={(e) => setCapital(e.target.value)}
            />
          </div>
          <div>
            <label className="label-caps block mb-1.5">Risk / trade (%)</label>
            <input
              type="number"
              step="0.1"
              className="input-dark num"
              value={riskPct}
              onChange={(e) => setRiskPct(e.target.value)}
            />
          </div>
        </div>
        <div className="mt-4 flex items-center gap-3 flex-wrap">
          <button className="btn-primary" onClick={run} disabled={loading}>
            {loading ? "Running backtest…" : "Run Backtest"}
          </button>
          {loading ? (
            <span className="text-sm text-gray-500">
              Fetching bars and simulating fills…
            </span>
          ) : null}
        </div>
      </section>

      {error ? (
        <div className="card p-5 border-red-500/40">
          <div className="text-red-400 font-semibold text-sm mb-1">
            Backtest failed
          </div>
          <div className="text-gray-400 text-sm num break-all">{error}</div>
        </div>
      ) : null}

      {!result && !loading && !error ? (
        <div className="card p-8 text-center text-sm text-gray-600">
          Configure a run and hit Run Backtest.
        </div>
      ) : null}

      {result ? (
        <>
          <section className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
            <Metric
              label="Total return"
              value={formatPct(result.total_return_pct, 2, true)}
              tone={result.total_return_pct >= 0 ? "green" : "red"}
            />
            <Metric
              label="Max drawdown"
              value={formatPct(-Math.abs(result.max_drawdown_pct), 2)}
              tone="red"
            />
            <Metric label="Sharpe" value={formatNumber(result.sharpe, 2)} />
            <Metric
              label="Win rate"
              value={formatPct(result.win_rate_pct, 1)}
              tone={result.win_rate_pct >= 50 ? "green" : "amber"}
            />
            <Metric
              label="Profit factor"
              value={formatNumber(result.profit_factor, 2)}
              tone={result.profit_factor >= 1 ? "green" : "red"}
            />
            <Metric
              label="Trades"
              value={formatNumber(result.trade_count, 0)}
              sub={`${result.bars} bars · ${result.strategy}`}
            />
          </section>

          <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="card p-5 lg:col-span-2">
              <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
                <div className="label-caps">Equity curve</div>
                <div className="text-[11px] text-gray-500 num">
                  start {formatINR(Number(capital))} → end{" "}
                  {formatINR(
                    (Number(capital) * (1 + result.total_return_pct / 100))
                  )}
                </div>
              </div>
              <EquityCurve values={result.equity_curve} />
              <div className="text-[11px] text-gray-600 mt-3">
                {result.data_label}
              </div>
            </div>

            <div className="card p-5 space-y-4">
              <div className="label-caps">Run details</div>
              <DetailRow k="Symbol" v={result.symbol} />
              <DetailRow k="Strategy" v={result.strategy} />
              <DetailRow k="Avg win" v={formatINR(result.avg_win)} tone="green" />
              <DetailRow k="Avg loss" v={formatINR(result.avg_loss)} tone="red" />
              <DetailRow
                k="Benchmark"
                v={formatPct(result.benchmark_return_pct, 2, true)}
              />
              <DetailRow
                k="Capital / risk"
                v={`${formatINR(Number(capital))} · ${riskPct}%`}
              />

              {result.assumptions?.length ? (
                <div>
                  <div className="label-caps mb-2">Assumptions</div>
                  <ul className="text-[12px] text-gray-500 space-y-1 list-disc pl-5">
                    {result.assumptions.map((a) => (
                      <li key={a}>{a}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {result.warnings?.length ? (
                <div>
                  <div className="label-caps mb-2">Warnings</div>
                  <ul className="text-[12px] text-amber-300/90 space-y-1 list-disc pl-5">
                    {result.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <p className="text-[11px] text-gray-600 border-t border-gray-800 pt-3">
                {result.note}
              </p>
            </div>
          </section>

          <section className="card overflow-x-auto">
            <div className="px-4 py-3 border-b border-gray-800">
              <span className="label-caps">Trades ({result.trades.length})</span>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-left">
                  <Th>Entry</Th>
                  <Th>Exit</Th>
                  <Th>Side</Th>
                  <Th>Qty</Th>
                  <Th>Entry ₹</Th>
                  <Th>Exit ₹</Th>
                  <Th>P&L</Th>
                  <Th>Fees</Th>
                  <Th>R</Th>
                  <Th>Exit reason</Th>
                </tr>
              </thead>
              <tbody>
                {result.trades.map((t, i) => (
                  <tr
                    key={`${t.entry_time}-${i}`}
                    className="border-b border-gray-800/60 hover:bg-gray-800/30"
                  >
                    <td className="px-3 py-2 num text-gray-400 whitespace-nowrap">
                      {formatTime(t.entry_time)}
                    </td>
                    <td className="px-3 py-2 num text-gray-400 whitespace-nowrap">
                      {formatTime(t.exit_time)}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                          t.side === "buy"
                            ? "bg-green/15 text-green border border-green/40"
                            : "bg-red/15 text-red border border-red/40"
                        }`}
                      >
                        {t.side.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-3 py-2 num">{t.qty}</td>
                    <td className="px-3 py-2 num">{formatINR(t.entry)}</td>
                    <td className="px-3 py-2 num">{formatINR(t.exit)}</td>
                    <td
                      className={`px-3 py-2 num ${
                        t.pnl > 0 ? "text-green" : "text-red"
                      }`}
                    >
                      {formatINRSigned(t.pnl)}
                    </td>
                    <td className="px-3 py-2 num text-gray-500">
                      {formatINR(t.fees)}
                    </td>
                    <td
                      className={`px-3 py-2 num ${
                        t.r > 0 ? "text-green" : "text-red"
                      }`}
                    >
                      {formatNumber(t.r, 2)}
                    </td>
                    <td className="px-3 py-2 text-[12px] text-gray-500">
                      {t.reason}
                    </td>
                  </tr>
                ))}
                {!result.trades.length ? (
                  <tr>
                    <td colSpan={10} className="px-3 py-8 text-center text-gray-600">
                      No trades triggered by this strategy on the selected data.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </section>
        </>
      ) : null}
    </div>
  );
}

function EquityCurve({ values }: { values: number[] }) {
  if (!values?.length) {
    return (
      <div className="h-56 flex items-center justify-center text-sm text-gray-600">
        No equity curve returned.
      </div>
    );
  }

  const width = 800;
  const height = 220;
  const pad = 8;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const stepX = values.length > 1 ? (width - pad * 2) / (values.length - 1) : 0;

  const points = values.map((v, i) => {
    const x = pad + i * stepX;
    const y = pad + (1 - (v - min) / range) * (height - pad * 2);
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });

  const last = values[values.length - 1];
  const first = values[0];
  const up = last >= first;
  const color = up ? "#10b981" : "#ef4444";
  const fillPoints = `${pad},${height - pad} ${points.join(
    " "
  )} ${pad + (values.length - 1) * stepX},${height - pad}`;

  return (
    <div className="w-full overflow-hidden">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-56"
        preserveAspectRatio="none"
        role="img"
        aria-label="equity curve"
      >
        <defs>
          <linearGradient id="eqFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.35" />
            <stop offset="100%" stopColor={color} stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((f) => (
          <line
            key={f}
            x1={pad}
            x2={width - pad}
            y1={pad + f * (height - pad * 2)}
            y2={pad + f * (height - pad * 2)}
            stroke="#1f2937"
            strokeWidth="1"
          />
        ))}
        <polygon points={fillPoints} fill="url(#eqFill)" />
        <polyline
          points={points.join(" ")}
          fill="none"
          stroke={color}
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <div className="flex items-center justify-between text-[11px] num text-gray-500 mt-1">
        <span>min {formatINR(min)}</span>
        <span>
          {values.length} points · max {formatINR(max)}
        </span>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "green" | "red" | "amber";
}) {
  const toneClass =
    tone === "green"
      ? "text-green"
      : tone === "red"
      ? "text-red"
      : tone === "amber"
      ? "text-amber-400"
      : "text-white";
  return (
    <div className="card p-4">
      <div className="label-caps">{label}</div>
      <div className={`num text-xl mt-2 ${toneClass}`}>{value}</div>
      {sub ? <div className="text-[11px] text-gray-500 mt-1">{sub}</div> : null}
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="px-3 py-2.5 label-caps font-medium whitespace-nowrap">
      {children}
    </th>
  );
}

function DetailRow({
  k,
  v,
  tone,
}: {
  k: string;
  v: string;
  tone?: "green" | "red";
}) {
  const cls = tone === "green" ? "text-green" : tone === "red" ? "text-red" : "text-gray-200";
  return (
    <div className="flex items-center justify-between gap-3 border-b border-gray-800/60 pb-1.5 text-sm">
      <span className="text-gray-500">{k}</span>
      <span className={`num ${cls}`}>{v}</span>
    </div>
  );
}
