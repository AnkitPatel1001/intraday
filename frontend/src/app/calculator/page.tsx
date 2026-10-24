"use client";

import { useCallback, useEffect, useState } from "react";
import { apiPost } from "@/lib/api";
import type { CostBreakdown, PlanResponse, TradePlan } from "@/lib/types";
import { formatINR, formatNumber, formatPct } from "@/lib/format";
import FreshnessBadge from "@/components/FreshnessBadge";

const STOP_RULES = [
  { value: "or_mid", label: "Opening range midpoint" },
  { value: "or_low", label: "Opening range low (long)" },
  { value: "or_high", label: "Opening range high (short)" },
  { value: "pct", label: "Percent stop (0.5%)" },
];

export default function CalculatorPage() {
  const [symbol, setSymbol] = useState("RELIANCE");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [entry, setEntry] = useState("2500");
  const [stop, setStop] = useState("2475");
  const [target, setTarget] = useState("2550");
  const [capital, setCapital] = useState("500000");
  const [riskPct, setRiskPct] = useState("1");
  const [qtyOverride, setQtyOverride] = useState("");
  const [entryBar, setEntryBar] = useState("5");
  const [stopRule, setStopRule] = useState("or_mid");
  const [targetR, setTargetR] = useState("2");

  const [costs, setCosts] = useState<CostBreakdown | null>(null);
  const [plan, setPlan] = useState<TradePlan | null>(null);
  const [planLabel, setPlanLabel] = useState<string>("");
  const [dataLabel, setDataLabel] = useState<string>("");
  const [costLoading, setCostLoading] = useState(false);
  const [planLoading, setPlanLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const entryN = Number(entry) || 0;
  const stopN = Number(stop) || 0;
  const targetN = Number(target) || 0;
  const capitalN = Number(capital) || 0;
  const riskN = Number(riskPct) || 0;

  const riskPerShare = Math.abs(entryN - stopN);
  const rewardPerShare = Math.abs(targetN - entryN);
  const rr = riskPerShare > 0 ? rewardPerShare / riskPerShare : 0;
  const riskAmount = (capitalN * riskN) / 100;
  const sizedQty =
    riskPerShare > 0 ? Math.floor(riskAmount / riskPerShare) : 0;
  const capitalCappedQty =
    entryN > 0 ? Math.min(sizedQty, Math.floor(capitalN / entryN)) : 0;
  const qty = qtyOverride !== "" ? Math.max(0, Number(qtyOverride) || 0) : capitalCappedQty;

  const fetchCosts = useCallback(async () => {
    if (entryN <= 0 || qty <= 0) {
      setCosts(null);
      return;
    }
    setCostLoading(true);
    try {
      const res = await apiPost<CostBreakdown>("/api/v1/trades/costs", {
        entry: entryN,
        qty,
        side,
      });
      setCosts(res);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCostLoading(false);
    }
  }, [entryN, qty, side]);

  useEffect(() => {
    const t = setTimeout(fetchCosts, 400);
    return () => clearTimeout(t);
  }, [fetchCosts]);

  const buildPlan = async () => {
    setPlanLoading(true);
    setError(null);
    try {
      const res = await apiPost<PlanResponse>("/api/v1/trades/plan", {
        symbol: symbol.toUpperCase(),
        side,
        entry_bar: Number(entryBar) || 5,
        stop_rule: stopRule,
        target_r: Number(targetR) || 2,
        capital: capitalN,
        risk_pct: riskN,
      });
      setPlan(res.plan);
      setPlanLabel(res.label);
      setDataLabel(res.data_label);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setPlan(null);
    } finally {
      setPlanLoading(false);
    }
  };

  const grossReward = rewardPerShare * qty;
  const netReward = grossReward - (costs?.total_est ?? 0);
  const costPct = costs ? costs.as_pct_of_turnover : 0;

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">Trade Calculator</h1>
          <p className="text-sm text-gray-500 mt-1">
            Position sizing, Indian intraday costs and reward:risk for a planned
            entry. Research only — not a buy/sell call.
          </p>
        </div>
        <span className="px-2 py-1 text-[10px] font-bold tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded">
          SIMULATED DATA
        </span>
      </header>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <section className="card p-5 space-y-4 xl:col-span-1 h-fit">
          <div className="label-caps">Inputs</div>

          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="label-caps block mb-1.5">Symbol</label>
              <input
                className="input-dark num uppercase"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
              />
            </div>
            <div>
              <label className="label-caps block mb-1.5">Side</label>
              <select
                className="input-dark"
                value={side}
                onChange={(e) => setSide(e.target.value as "buy" | "sell")}
              >
                <option value="buy">BUY (long)</option>
                <option value="sell">SELL (short)</option>
              </select>
            </div>
            <div>
              <label className="label-caps block mb-1.5">Entry bar</label>
              <input
                type="number"
                className="input-dark num"
                value={entryBar}
                onChange={(e) => setEntryBar(e.target.value)}
                min={0}
              />
            </div>
            <div>
              <label className="label-caps block mb-1.5">Entry (₹)</label>
              <input
                type="number"
                className="input-dark num"
                value={entry}
                onChange={(e) => setEntry(e.target.value)}
                step="0.05"
              />
            </div>
            <div>
              <label className="label-caps block mb-1.5">Stop (₹)</label>
              <input
                type="number"
                className="input-dark num"
                value={stop}
                onChange={(e) => setStop(e.target.value)}
                step="0.05"
              />
            </div>
            <div>
              <label className="label-caps block mb-1.5">Target (₹)</label>
              <input
                type="number"
                className="input-dark num"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                step="0.05"
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
                className="input-dark num"
                value={riskPct}
                onChange={(e) => setRiskPct(e.target.value)}
                step="0.1"
              />
            </div>
            <div>
              <label className="label-caps block mb-1.5">Qty (blank = auto)</label>
              <input
                type="number"
                className="input-dark num"
                placeholder={String(capitalCappedQty)}
                value={qtyOverride}
                onChange={(e) => setQtyOverride(e.target.value)}
                min={0}
              />
            </div>
            <div>
              <label className="label-caps block mb-1.5">Stop rule</label>
              <select
                className="input-dark"
                value={stopRule}
                onChange={(e) => setStopRule(e.target.value)}
              >
                {STOP_RULES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-span-2">
              <label className="label-caps block mb-1.5">Target R</label>
              <input
                type="number"
                className="input-dark num"
                value={targetR}
                onChange={(e) => setTargetR(e.target.value)}
                step="0.1"
              />
            </div>
          </div>

          <button
            className="btn-primary w-full"
            onClick={buildPlan}
            disabled={planLoading}
          >
            {planLoading ? "Building plan…" : "Build plan via API"}
          </button>

          {error ? (
            <div className="text-xs text-red-400 num break-all border border-red-500/30 rounded p-2 bg-red-500/5">
              {error}
            </div>
          ) : null}
        </section>

        <section className="xl:col-span-2 space-y-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Metric
              label="Position size"
              value={`${formatNumber(qty, 0)} shares`}
              sub={
                qtyOverride === ""
                  ? `auto-sized (capped ${formatNumber(capitalCappedQty, 0)})`
                  : "manual override"
              }
            />
            <Metric
              label="Capital deployed"
              value={formatINR(qty * entryN)}
              sub={`${formatPct(
                capitalN > 0 ? (qty * entryN * 100) / capitalN : 0,
                1
              )} of capital`}
            />
            <Metric
              label="Risk (to stop)"
              value={formatINR(riskPerShare * qty)}
              sub={`${formatINR(riskPerShare)}/share · budget ${formatINR(
                riskAmount
              )}`}
              tone="red"
            />
            <Metric
              label="Reward (to target)"
              value={formatINR(rewardPerShare * qty)}
              sub={`${formatINR(rewardPerShare)}/share`}
              tone="green"
            />
          </div>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Metric
              label="Reward : Risk"
              value={rr > 0 ? `1 : ${formatNumber(rr, 2)}` : "—"}
              sub={
                rr >= 2
                  ? "≥ 2R target"
                  : rr > 0
                  ? "below 2R"
                  : "invalid stop/entry"
              }
              tone={rr >= 2 ? "green" : rr > 0 ? "amber" : "red"}
            />
            <Metric
              label="Risk per share"
              value={formatINR(riskPerShare)}
              sub={`entry ${formatINR(entryN)} · stop ${formatINR(stopN)}`}
            />
            <Metric
              label="Est. round-trip cost"
              value={costs ? formatINR(costs.total_est) : "—"}
              sub={
                costLoading
                  ? "calculating…"
                  : costs
                  ? `${formatNumber(costs.as_pct_of_turnover, 3)}% of turnover`
                  : "awaiting inputs"
              }
            />
            <Metric
              label="Net reward after cost"
              value={costs ? formatINR(netReward) : "—"}
              sub={
                costs && grossReward > 0
                  ? `${formatPct((netReward / grossReward) * 100, 1)} of gross`
                  : "—"
              }
              tone={netReward > 0 ? "green" : "red"}
            />
          </div>

          <div className="card p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="label-caps">Cost breakdown (INR)</div>
              {costLoading ? (
                <span className="text-[11px] text-gray-500">updating…</span>
              ) : null}
            </div>
            {costs ? (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-x-6 gap-y-2 text-sm">
                <CostRow k="Brokerage" v={costs.brokerage} />
                <CostRow k="STT" v={costs.stt} />
                <CostRow k="Exchange charges" v={costs.exchange_charges} />
                <CostRow k="SEBI fees" v={costs.sebi_fees} />
                <CostRow k="Stamp duty" v={costs.stamp_duty} />
                <CostRow k="GST" v={costs.gst} />
                <CostRow k="Slippage (est.)" v={costs.slippage_est} />
                <CostRow k="Total" v={costs.total_est} strong />
                <CostRow
                  k="% of turnover"
                  v={costs.as_pct_of_turnover}
                  pct
                  strong
                />
              </div>
            ) : (
              <div className="text-sm text-gray-600">
                Enter a valid entry price and quantity to estimate costs.
              </div>
            )}
            <div className="text-[11px] text-gray-600 mt-3">
              Approximate FY 2025-26 intraday Indian charges. Actual broker
              pricing varies. Cost drag at this size:{" "}
              <span className="num text-gray-400">{formatPct(costPct, 3)}</span>{" "}
              per side of turnover.
            </div>
          </div>

          <div className="card p-5">
            <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
              <div className="label-caps">API trade plan</div>
              <div className="flex items-center gap-2">
                {plan ? <FreshnessBadge freshness="simulated" source="planner" /> : null}
              </div>
            </div>
            {plan ? (
              <div className="space-y-3">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <Metric label="Plan entry" value={formatINR(plan.entry)} />
                  <Metric label="Plan stop" value={formatINR(plan.stop)} tone="red" />
                  <Metric
                    label="Plan target"
                    value={formatINR(plan.target)}
                    tone="green"
                  />
                  <Metric
                    label="Plan R:R"
                    value={`1 : ${formatNumber(plan.risk_reward, 2)}`}
                  />
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <MiniField k="Setup" v={plan.setup} />
                  <MiniField k="Entry time" v={plan.entry_time} />
                  <MiniField k="Stop rule" v={plan.stop_rule} />
                  <MiniField k="Max holding" v={`${plan.max_holding_bars} bars`} />
                </div>
                <div className="text-[12px] text-gray-400 leading-relaxed">
                  <span className="text-gray-500">Invalidation:</span>{" "}
                  {plan.invalidation}
                </div>
                {plan.warnings?.length ? (
                  <ul className="text-[12px] text-amber-300/90 space-y-1 list-disc pl-5">
                    {plan.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                ) : null}
                <div className="text-[11px] text-gray-600 border-t border-gray-800 pt-3">
                  {planLabel}
                  {dataLabel ? ` · ${dataLabel}` : ""}
                </div>
              </div>
            ) : (
              <div className="text-sm text-gray-600">
                No plan built yet. Use the button on the left to pull a plan from{" "}
                <span className="num">POST /trades/plan</span>.
              </div>
            )}
          </div>
        </section>
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
      <div className={`num text-lg mt-2 ${toneClass}`}>{value}</div>
      {sub ? <div className="text-[11px] text-gray-500 mt-1">{sub}</div> : null}
    </div>
  );
}

function CostRow({
  k,
  v,
  pct,
  strong,
}: {
  k: string;
  v: number;
  pct?: boolean;
  strong?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-gray-800/60 py-1.5">
      <span className={strong ? "text-gray-300" : "text-gray-500"}>{k}</span>
      <span
        className={`num ${strong ? "text-white font-semibold" : "text-gray-200"}`}
      >
        {pct ? formatNumber(v, 4) + "%" : formatINR(v)}
      </span>
    </div>
  );
}

function MiniField({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div className="label-caps">{k}</div>
      <div className="num text-gray-200 mt-1">{v}</div>
    </div>
  );
}
