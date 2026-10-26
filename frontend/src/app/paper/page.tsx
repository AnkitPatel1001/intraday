"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import type {
  OrderResponse,
  PerformanceResponse,
  Portfolio,
} from "@/lib/types";
import { formatINR, formatINRSigned, formatNumber, formatPct } from "@/lib/format";

export default function PaperTradingPage() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [performance, setPerformance] = useState<PerformanceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [symbol, setSymbol] = useState("RELIANCE");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [qty, setQty] = useState("10");
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [placing, setPlacing] = useState(false);
  const [orderMsg, setOrderMsg] = useState<string | null>(null);
  const [orderErr, setOrderErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pf, perf] = await Promise.all([
        apiGet<Portfolio>("/api/v1/paper/portfolio"),
        apiGet<PerformanceResponse>("/api/v1/analytics/performance").catch(
          () => null
        ),
      ]);
      setPortfolio(pf);
      setPerformance(perf);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const placeOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    setPlacing(true);
    setOrderMsg(null);
    setOrderErr(null);
    try {
      const res = await apiPost<OrderResponse>("/api/v1/paper/order", {
        symbol: symbol.toUpperCase().trim(),
        side,
        qty: Number(qty),
        order_type: orderType,
      });
      setPortfolio(res.portfolio);
      setOrderMsg(
        `Order ${res.order.id} ${res.order.status} @ ${formatINR(
          res.order.fill_price
        )} · fees ${formatINR(res.order.fees)}`
      );
      // refresh analytics after fill
      apiGet<PerformanceResponse>("/api/v1/analytics/performance")
        .then(setPerformance)
        .catch(() => undefined);
    } catch (err) {
      setOrderErr(err instanceof Error ? err.message : String(err));
    } finally {
      setPlacing(false);
    }
  };

  const positions = portfolio?.positions ?? [];
  const unrealized = positions.reduce((s, p) => s + (p.unrealized_pnl ?? 0), 0);
  const equity =
    (portfolio?.cash ?? 0) +
    positions.reduce((s, p) => s + p.qty * p.avg_price, 0);

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">Paper Trading</h1>
          <p className="text-sm text-gray-500 mt-1">
            Simulated fills against demo quotes. No real money, no broker link.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="px-2 py-1 text-[10px] font-bold tracking-wider bg-purple-500/20 text-purple-300 border border-purple-500/40 rounded">
            PAPER TRADING
          </span>
          <span className="px-2 py-1 text-[10px] font-bold tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded">
            SIMULATED DATA
          </span>
          <button className="btn-ghost text-xs" onClick={load} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>

      {error ? (
        <div className="card p-5 border-red-500/40">
          <div className="text-red-400 font-semibold text-sm mb-1">
            Failed to load portfolio
          </div>
          <div className="text-gray-400 text-sm num break-all">{error}</div>
          <button className="btn-primary mt-3" onClick={load}>
            Retry
          </button>
        </div>
      ) : null}

      {loading && !portfolio ? (
        <div className="card p-8 text-center text-sm text-gray-500">
          Loading paper portfolio…
        </div>
      ) : null}

      {portfolio ? (
        <>
          <section className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            <Card label="Cash" value={formatINR(portfolio.cash)} />
            <Card label="Positions value" value={formatINR(
              positions.reduce((s, p) => s + p.qty * p.avg_price, 0)
            )} />
            <Card
              label="Unrealized P&L"
              value={formatINRSigned(unrealized)}
              tone={unrealized > 0 ? "green" : unrealized < 0 ? "red" : undefined}
            />
            <Card
              label="Realized P&L"
              value={formatINRSigned(portfolio.realized_pnl)}
              tone={
                portfolio.realized_pnl > 0
                  ? "green"
                  : portfolio.realized_pnl < 0
                  ? "red"
                  : undefined
              }
            />
            <Card label="Total fees" value={formatINR(portfolio.total_fees)} />
          </section>

          <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="card p-5 lg:col-span-1 h-fit">
              <div className="label-caps mb-3">Place order (simulated)</div>
              <form onSubmit={placeOrder} className="space-y-3">
                <div>
                  <label className="label-caps block mb-1.5">Symbol</label>
                  <input
                    className="input-dark num uppercase"
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value)}
                    required
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="label-caps block mb-1.5">Side</label>
                    <select
                      className="input-dark"
                      value={side}
                      onChange={(e) => setSide(e.target.value as "buy" | "sell")}
                    >
                      <option value="buy">BUY</option>
                      <option value="sell">SELL</option>
                    </select>
                  </div>
                  <div>
                    <label className="label-caps block mb-1.5">Qty</label>
                    <input
                      type="number"
                      min={1}
                      className="input-dark num"
                      value={qty}
                      onChange={(e) => setQty(e.target.value)}
                      required
                    />
                  </div>
                </div>
                <div>
                  <label className="label-caps block mb-1.5">Order type</label>
                  <select
                    className="input-dark"
                    value={orderType}
                    onChange={(e) =>
                      setOrderType(e.target.value as "market" | "limit")
                    }
                  >
                    <option value="market">Market</option>
                    <option value="limit">Limit</option>
                  </select>
                </div>
                <button className="btn-primary w-full" disabled={placing}>
                  {placing ? "Submitting…" : "Submit order"}
                </button>
              </form>

              {orderMsg ? (
                <div className="mt-3 text-xs num text-green border border-green/40 bg-green/10 rounded p-2">
                  {orderMsg}
                </div>
              ) : null}
              {orderErr ? (
                <div className="mt-3 text-xs num text-red border border-red/40 bg-red/10 rounded p-2 break-all">
                  {orderErr}
                </div>
              ) : null}

              <div className="text-[11px] text-gray-600 mt-4 leading-relaxed">
                Market orders fill at the current demo quote (slippage and fees
                applied by the engine). {portfolio.label}
              </div>
            </div>

            <div className="lg:col-span-2 space-y-6">
              <div className="card overflow-x-auto">
                <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
                  <span className="label-caps">Open positions</span>
                  <span className="text-[11px] text-gray-600 num">
                    {positions.length} open · equity≈ {formatINR(equity)}
                  </span>
                </div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800 text-left">
                      <Th>Symbol</Th>
                      <Th>Side</Th>
                      <Th>Qty</Th>
                      <Th>Avg price</Th>
                      <Th>Stop</Th>
                      <Th>Target</Th>
                      <Th>Unrealized P&L</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((p) => (
                      <tr
                        key={`${p.symbol}-${p.side}`}
                        className="border-b border-gray-800/60 hover:bg-gray-800/30"
                      >
                        <td className="px-4 py-2.5 num font-semibold text-white">
                          {p.symbol}
                        </td>
                        <td className="px-4 py-2.5">
                          <span
                            className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                              p.side === "buy"
                                ? "bg-green/15 text-green border border-green/40"
                                : "bg-red/15 text-red border border-red/40"
                            }`}
                          >
                            {p.side.toUpperCase()}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 num">{p.qty}</td>
                        <td className="px-4 py-2.5 num">{formatINR(p.avg_price)}</td>
                        <td className="px-4 py-2.5 num text-gray-400">
                          {p.stop ? formatINR(p.stop) : "—"}
                        </td>
                        <td className="px-4 py-2.5 num text-gray-400">
                          {p.target ? formatINR(p.target) : "—"}
                        </td>
                        <td
                          className={`px-4 py-2.5 num ${
                            p.unrealized_pnl > 0
                              ? "text-green"
                              : p.unrealized_pnl < 0
                              ? "text-red"
                              : "text-gray-400"
                          }`}
                        >
                          {formatINRSigned(p.unrealized_pnl)}
                        </td>
                      </tr>
                    ))}
                    {!positions.length ? (
                      <tr>
                        <td colSpan={7} className="px-4 py-8 text-center text-gray-600">
                          No open positions. Place a simulated order.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>

              <div className="card p-5">
                <div className="label-caps mb-3">Performance (closed trades)</div>
                {performance ? (
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                    <Card
                      label="Realized P&L"
                      value={formatINRSigned(performance.realized_pnl)}
                      tone={
                        performance.realized_pnl > 0
                          ? "green"
                          : performance.realized_pnl < 0
                          ? "red"
                          : undefined
                      }
                      flat
                    />
                    <Card
                      label="Win rate"
                      value={formatPct(performance.win_rate_pct, 1)}
                      flat
                    />
                    <Card
                      label="Profit factor"
                      value={formatNumber(performance.profit_factor, 2)}
                      flat
                    />
                    <Card
                      label="Trades"
                      value={formatNumber(performance.trade_count, 0)}
                      flat
                    />
                    <Card
                      label="Fees paid"
                      value={formatINR(performance.total_fees ?? portfolio.total_fees)}
                      flat
                    />
                  </div>
                ) : (
                  <div className="text-sm text-gray-600">
                    Analytics unavailable — place a trade to generate results.
                  </div>
                )}
                <div className="text-[11px] text-gray-600 mt-3">
                  {performance?.label ?? portfolio.label}
                </div>

                {performance?.closed_trades?.length ? (
                  <div className="mt-4 border-t border-gray-800 pt-3">
                    <div className="label-caps mb-2">Recent closed</div>
                    <div className="space-y-1.5 max-h-44 overflow-y-auto pr-1">
                      {performance.closed_trades.map((t, i) => (
                        <div
                          key={`${t.symbol}-${i}`}
                          className="flex items-center justify-between text-xs border-b border-gray-800/60 pb-1.5"
                        >
                          <span className="num text-gray-300">
                            {t.symbol} · {t.qty} @ {formatINR(t.avg_price)}
                          </span>
                          <span
                            className={`num ${
                              t.pnl > 0 ? "text-green" : "text-red"
                            }`}
                          >
                            {formatINRSigned(t.pnl)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="px-4 py-2.5 label-caps font-medium whitespace-nowrap">
      {children}
    </th>
  );
}

function Card({
  label,
  value,
  tone,
  flat,
}: {
  label: string;
  value: string;
  tone?: "green" | "red";
  flat?: boolean;
}) {
  const toneClass =
    tone === "green" ? "text-green" : tone === "red" ? "text-red" : "text-white";
  return (
    <div className={`${flat ? "bg-[#0d1321]" : "card"} p-4`}>
      <div className="label-caps">{label}</div>
      <div className={`num text-lg mt-2 ${toneClass}`}>{value}</div>
    </div>
  );
}
