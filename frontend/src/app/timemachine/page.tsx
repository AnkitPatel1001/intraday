"use client";

import { useEffect, useRef, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import type { Quote, TimeMachineRequest, TimeMachineResponse } from "@/lib/types";
import { formatINR, formatINRSigned, formatNumber, formatPct } from "@/lib/format";
import { deriveLevels, autoOdds, type Levels } from "@/lib/tm";
import FreshnessBadge from "@/components/FreshnessBadge";

export default function TimeMachinePage() {
  const [symbol, setSymbol] = useState("RELIANCE");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [entry, setEntry] = useState("2500");
  const [stop, setStop] = useState("2475");
  const [target, setTarget] = useState("2550");
  const [entryBar, setEntryBar] = useState("5");
  const [replays, setReplays] = useState("10000");
  const [seed, setSeed] = useState("19");

  const [ltp, setLtp] = useState<number | null>(null);
  const [ltpInfo, setLtpInfo] = useState("");
  const [ltpError, setLtpError] = useState<string | null>(null);
  const fetchSeq = useRef(0);

  const [result, setResult] = useState<TimeMachineResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Auto run: levels derived from live price, fixed skill defaults
  // (10,000 replays, seed 19) — hit counts + ₹ amounts per stock.
  const [autoQty, setAutoQty] = useState("10");
  const [autoRunning, setAutoRunning] = useState(false);
  const [autoErr, setAutoErr] = useState<string | null>(null);
  const [autoRes, setAutoRes] = useState<TimeMachineResponse | null>(null);
  const [autoLevels, setAutoLevels] = useState<Levels | null>(null);

  const fillFromLtp = async (sym: string, why: "auto" | "manual") => {
    const seq = ++fetchSeq.current;
    try {
      const q = await apiGet<Quote>(
        `/api/v1/market/quote/${encodeURIComponent(sym)}`
      );
      if (seq !== fetchSeq.current) return; // stale: a newer fetch superseded it
      const lv = deriveLevels(q.last_price, side);
      setEntry(String(lv.entry));
      setStop(String(lv.stop));
      setTarget(String(lv.target));
      setLtp(q.last_price);
      setLtpInfo([q.source, q.label || q.freshness].filter(Boolean).join(" · "));
      setLtpError(null);
      if (why === "manual") setError(null);
    } catch (err) {
      if (seq !== fetchSeq.current) return;
      const msg = err instanceof Error ? err.message : String(err);
      setLtpError(msg);
      if (why === "manual") setError(`live price unavailable: ${msg}`);
    }
  };

  // Symbol changed -> debounced fetch of the live price, entry/stop/target
  // re-derived from it (the old values were never refreshed before).
  useEffect(() => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;
    const t = setTimeout(() => {
      void fillFromLtp(sym, "auto");
    }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  // Side flipped -> re-derive stop/target from the last live price.
  useEffect(() => {
    if (ltp == null) return;
    const lv = deriveLevels(ltp, side);
    setEntry(String(lv.entry));
    setStop(String(lv.stop));
    setTarget(String(lv.target));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [side]);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const body: TimeMachineRequest = {
        symbol: symbol.toUpperCase(),
        side,
        entry: Number(entry),
        stop: Number(stop),
        target: Number(target),
        entry_bar: Number(entryBar) || 5,
        replays: Math.min(100000, Math.max(1, Number(replays) || 10000)),
        seed: Number(seed) || 19,
      };
      if (!body.entry || !body.stop || !body.target) {
        throw new Error("entry, stop and target are required numbers");
      }
      const res = await apiPost<TimeMachineResponse>(
        "/api/v1/trades/timemachine",
        body
      );
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const mc = result?.mc;
  const history = result?.history;

  const runAuto = async () => {
    const sym = symbol.trim().toUpperCase();
    if (!sym) {
      setAutoErr("enter a symbol first");
      return;
    }
    setAutoRunning(true);
    setAutoErr(null);
    try {
      const q = await apiGet<Quote>(
        `/api/v1/market/quote/${encodeURIComponent(sym)}`
      );
      const lv = deriveLevels(q.last_price, side);
      const res = await apiPost<TimeMachineResponse>(
        "/api/v1/trades/timemachine",
        {
          symbol: sym,
          side,
          entry: lv.entry,
          stop: lv.stop,
          target: lv.target,
          entry_bar: Number(entryBar) || 5,
          replays: 10000,
          seed: 19,
        }
      );
      setAutoRes(res);
      setAutoLevels(lv);
    } catch (err) {
      setAutoErr(err instanceof Error ? err.message : String(err));
      setAutoRes(null);
      setAutoLevels(null);
    } finally {
      setAutoRunning(false);
    }
  };

  const autoMc = autoRes?.mc;
  const autoQtyNum = Math.max(1, Number(autoQty) || 1);
  const odds =
    autoMc && autoLevels
      ? autoOdds(autoMc, autoLevels, side, autoQtyNum)
      : null;

  const bars = [
    {
      key: "target",
      label: "Hit target",
      pct: (mc?.p_target ?? 0) * 100,
      color: "bg-green",
      text: "text-green",
    },
    {
      key: "stop",
      label: "Hit stop",
      pct: (mc?.p_stop ?? 0) * 100,
      color: "bg-red",
      text: "text-red",
    },
    {
      key: "neither",
      label: "Neither (session close)",
      pct: (mc?.p_neither ?? 0) * 100,
      color: "bg-gray-500",
      text: "text-gray-300",
    },
  ];

  const verdictTone = (v: string): string => {
    const u = (v || "").toUpperCase();
    if (
      u.includes("AVOID") ||
      u.includes("POOR") ||
      u.includes("WEAK") ||
      u.includes("NO EDGE") ||
      u.includes("UNFAVOR")
    ) {
      return "text-red border-red/40 bg-red/10";
    }
    if (
      u.includes("FAVOR") ||
      u.includes("GOOD") ||
      u.includes("STRONG") ||
      u.includes("EDGE")
    ) {
      return "text-green border-green/40 bg-green/10";
    }
    return "text-amber-300 border-amber-500/40 bg-amber-500/10";
  };

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">Time Machine</h1>
          <p className="text-sm text-gray-500 mt-1">
            Replay a planned entry: Monte Carlo path simulation + historical rule
            replay over past sessions. Simulation, not a forecast.
          </p>
        </div>
        <span className="px-2 py-1 text-[10px] font-bold tracking-wider bg-purple-500/20 text-purple-300 border border-purple-500/40 rounded">
          SIMULATED DATA
        </span>
      </header>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <section className="card p-5 space-y-4 h-fit">
          <div className="label-caps">Trade plan inputs</div>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="label-caps block mb-1.5">Symbol</label>
              <input
                className="input-dark num uppercase"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
              />
              <div className="flex items-center justify-between gap-2 mt-1.5 flex-wrap">
                <span className="text-[11px] num text-gray-500">
                  {ltp != null ? (
                    <>
                      LTP {formatINR(ltp)}
                      {ltpInfo ? <span className="text-gray-600"> · {ltpInfo}</span> : null}
                    </>
                  ) : ltpError ? (
                    <span className="text-amber-400">live price unavailable</span>
                  ) : (
                    "fetching live price…"
                  )}
                </span>
                <button
                  className="btn-ghost text-[10px] px-2 py-0.5"
                  onClick={() => {
                    const sym = symbol.trim().toUpperCase();
                    if (sym) void fillFromLtp(sym, "manual");
                  }}
                  disabled={loading}
                >
                  Fill from live price
                </button>
              </div>
            </div>
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
              <label className="label-caps block mb-1.5">Replays (max 100,000)</label>
              <input
                type="number"
                className="input-dark num"
                value={replays}
                onChange={(e) => setReplays(e.target.value)}
                min={100}
                max={100000}
              />
            </div>
            <div className="col-span-2">
              <label className="label-caps block mb-1.5">Seed</label>
              <input
                type="number"
                className="input-dark num"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
              />
            </div>
          </div>

          <button className="btn-primary w-full" onClick={run} disabled={loading}>
            {loading ? "Running replays…" : "Run Time Machine"}
          </button>
          <p className="text-[11px] text-gray-600 leading-relaxed">
            Backend replays entry bar → session close across Monte Carlo paths and
            historical sessions pooled from ~90 days of 5m bars.
          </p>

          {error ? (
            <div className="text-xs text-red-400 num break-all border border-red-500/30 rounded p-2 bg-red-500/5">
              {error}
            </div>
          ) : null}
        </section>

        <section className="xl:col-span-2 space-y-6">
          {!result && !loading ? (
            <div className="card p-10 text-center text-sm text-gray-600">
              Enter entry/stop/target and run the simulation to see probability
              bars, verdict and historical outcomes.
            </div>
          ) : null}

          {loading ? (
            <div className="card p-10 text-center text-sm text-gray-500">
              Simulating {formatNumber(Number(replays) || 0, 0)} replays…
            </div>
          ) : null}

          {result && mc ? (
            <>
              {result.warnings && result.warnings.length > 0 ? (
                <div className="text-xs text-amber-300 border border-amber-500/40 bg-amber-500/10 rounded p-3 num">
                  {result.warnings.map((w, i) => (
                    <div key={i}>Note: {w}.</div>
                  ))}
                </div>
              ) : null}
              <div className="card p-5">
                <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
                  <div className="label-caps">
                    Monte Carlo outcome ({formatNumber(mc.pool_sessions, 0)} sessions
                    pool · seed {mc.seed})
                  </div>
                  <FreshnessBadge freshness="simulated" source="monte carlo" />
                </div>

                <div className="space-y-4">
                  {bars.map((b) => (
                    <div key={b.key}>
                      <div className="flex items-center justify-between text-sm mb-1.5">
                        <span className="text-gray-400">{b.label}</span>
                        <span className={`num font-semibold ${b.text}`}>
                          {formatPct(b.pct, 1)}
                        </span>
                      </div>
                      <div className="h-5 bg-[#0d1321] border border-gray-800 rounded overflow-hidden">
                        <div
                          className={`h-full ${b.color} transition-all duration-700`}
                          style={{ width: `${Math.min(100, Math.max(0, b.pct))}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-5">
                  <Mini label="P(green / ≥0R)" v={formatPct((mc.p_green ?? 0) * 100, 1)} tone="green" />
                  <Mini label="Avg R" v={mc.avg_R === null ? "—" : formatNumber(mc.avg_R, 2)} />
                  <Mini label="Median close" v={formatINR(mc.median_close)} />
                  <Mini
                    label="R at target"
                    v={mc.r_at_target === null ? "—" : formatNumber(mc.r_at_target, 2)}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="card p-5">
                  <div className="label-caps mb-3">Verdict</div>
                  <div
                    className={`inline-block px-4 py-3 rounded border text-lg font-bold num ${verdictTone(
                      result.verdict
                    )}`}
                  >
                    {result.verdict}
                  </div>
                  <ul className="mt-4 space-y-2 text-sm text-gray-400 list-disc pl-5">
                    {(Array.isArray(result.verdict_notes)
                      ? result.verdict_notes
                      : [result.verdict_notes]
                    )
                      .filter(Boolean)
                      .map((n, i) => (
                        <li key={i}>{n}</li>
                      ))}
                  </ul>
                  {result.note ? (
                    <p className="text-[11px] text-gray-600 mt-4 border-t border-gray-800 pt-3">
                      {result.note}
                    </p>
                  ) : null}
                </div>

                <div className="card p-5">
                  <div className="label-caps mb-3">Historical rule replay</div>
                  {history ? (
                    <div className="space-y-2.5 text-sm">
                      <HistRow k="Sessions pooled" v={formatNumber(history.sessions, 0)} />
                      <HistRow k="Trades triggered" v={formatNumber(history.triggered, 0)} />
                      <HistRow
                        k="Closed at target"
                        v={history.target === null ? "—" : formatNumber(history.target, 0)}
                        tone="green"
                      />
                      <HistRow
                        k="Closed at stop"
                        v={history.stop === null ? "—" : formatNumber(history.stop, 0)}
                        tone="red"
                      />
                      <HistRow
                        k="Closed at session end"
                        v={history.close === null ? "—" : formatNumber(history.close, 0)}
                      />
                      <HistRow
                        k="Avg R"
                        v={history.avg_R === null ? "—" : formatNumber(history.avg_R, 2)}
                      />
                    </div>
                  ) : (
                    <div className="text-sm text-gray-600">No history returned.</div>
                  )}
                  {history?.note ? (
                    <p className="text-[11px] text-gray-600 mt-3">{history.note}</p>
                  ) : null}
                  <div className="text-[11px] text-gray-600 mt-4 border-t border-gray-800 pt-3">
                    Historical replay applies the same entry/stop/target rules to
                    past sessions — costs excluded, entry bar fixed.
                  </div>
                </div>
              </div>

              <div className="card p-5">
                <div className="label-caps mb-3">Simulated plan</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <Mini label="Symbol" v={String(result.plan?.symbol ?? symbol)} />
                  <Mini label="Side" v={String(result.plan?.side ?? side)} />
                  <Mini
                    label="Entry"
                    v={formatINR(Number(result.plan?.entry ?? entry))}
                  />
                  <Mini
                    label="Stop"
                    v={formatINR(Number(result.plan?.stop ?? stop))}
                    tone="red"
                  />
                  <Mini
                    label="Target"
                    v={formatINR(Number(result.plan?.target ?? target))}
                    tone="green"
                  />
                  <Mini
                    label="Entry bar"
                    v={String(result.plan?.entry_bar ?? entryBar)}
                  />
                  <Mini label="Setup" v={String(result.plan?.setup ?? "—")} />
                  <Mini label="Entry time" v={String(result.plan?.entry_time ?? "—")} />
                  <Mini label="Bars left" v={formatNumber(mc.bars_left, 0)} />
                </div>
              </div>

              {result.report ? (
                <div className="card p-5">
                  <div className="label-caps mb-3">
                    Skill report — trader-timemachine format
                  </div>
                  <pre className="text-[11px] leading-relaxed text-gray-300 whitespace-pre-wrap num">
                    {result.report}
                  </pre>
                </div>
              ) : null}
            </>
          ) : null}
        </section>
      </div>

      <section className="card p-5 space-y-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <div className="label-caps">
              Auto run — skill odds for this stock
            </div>
            <p className="text-[11px] text-gray-600 mt-1 leading-relaxed">
              One click: entry/stop/target auto-derived from the live price,
              then 10,000 trader-timemachine replays (seed 19). Exact hit counts
              and ₹ per share / totals for your qty.
            </p>
          </div>
          <FreshnessBadge freshness="simulated" source="skill engine" />
        </div>

        <div className="flex items-end gap-3 flex-wrap">
          <div>
            <label className="label-caps block mb-1.5">Qty (for ₹ totals)</label>
            <input
              type="number"
              min={1}
              className="input-dark num w-28"
              value={autoQty}
              onChange={(e) => setAutoQty(e.target.value)}
            />
          </div>
          <button
            className="btn-primary"
            onClick={runAuto}
            disabled={autoRunning}
          >
            {autoRunning
              ? "Running 10,000 replays…"
              : `Auto run: ${symbol.trim().toUpperCase() || "—"}`}
          </button>
        </div>

        {autoErr ? (
          <div className="text-xs text-red-400 num break-all border border-red-500/30 rounded p-2 bg-red-500/5">
            {autoErr}
          </div>
        ) : null}

        {autoRes && autoMc && odds && autoLevels ? (
          <>
            {autoRes.warnings && autoRes.warnings.length > 0 ? (
              <div className="text-[11px] text-amber-300 border border-amber-500/40 bg-amber-500/10 rounded p-2 num">
                {autoRes.warnings.map((w, i) => (
                  <div key={i}>Note: {w}.</div>
                ))}
              </div>
            ) : null}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-[#0d1321] border border-green/40 rounded p-4">
                <div className="label-caps">Hit target</div>
                <div className="num text-2xl mt-1 text-green">
                  {formatNumber(odds.targetCount, 0)}{" "}
                  <span className="text-sm text-gray-500">
                    / {formatNumber(odds.replays, 0)}
                  </span>
                </div>
                <div className="num text-sm text-green mt-1">
                  {formatPct((odds.targetCount / odds.replays) * 100, 1)}
                </div>
                <div className="text-xs text-gray-400 mt-2 num leading-relaxed">
                  +{formatINR(odds.rewardPerShare)} / share
                  <br />
                  +{formatINR(odds.rewardTotal)} for {autoQtyNum} qty
                </div>
              </div>

              <div className="bg-[#0d1321] border border-red/40 rounded p-4">
                <div className="label-caps">Hit stop</div>
                <div className="num text-2xl mt-1 text-red">
                  {formatNumber(odds.stopCount, 0)}{" "}
                  <span className="text-sm text-gray-500">
                    / {formatNumber(odds.replays, 0)}
                  </span>
                </div>
                <div className="num text-sm text-red mt-1">
                  {formatPct((odds.stopCount / odds.replays) * 100, 1)}
                </div>
                <div className="text-xs text-gray-400 mt-2 num leading-relaxed">
                  −{formatINR(odds.riskPerShare)} / share
                  <br />−{formatINR(odds.riskTotal)} for {autoQtyNum} qty
                </div>
              </div>

              <div className="bg-[#0d1321] border border-gray-800 rounded p-4">
                <div className="label-caps">Neither (session end)</div>
                <div className="num text-2xl mt-1 text-gray-300">
                  {formatNumber(odds.neitherCount, 0)}{" "}
                  <span className="text-sm text-gray-500">
                    / {formatNumber(odds.replays, 0)}
                  </span>
                </div>
                <div className="num text-sm text-gray-500 mt-1">
                  {formatPct((odds.neitherCount / odds.replays) * 100, 1)}
                </div>
                <div className="text-xs text-gray-600 mt-2 leading-relaxed">
                  Closed at {autoMc.until ?? "15:30"} without either level
                </div>
              </div>
            </div>

            <div className="border-t border-gray-800 pt-3 space-y-2">
              <div className="label-caps">
                Price reach — how many replays touched the level
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="bg-[#0d1321] border border-green/30 rounded p-3">
                  <div className="flex items-center justify-between gap-2 text-sm flex-wrap">
                    <span className="text-gray-400 num">
                      Reached {formatINR(autoLevels.target)}
                    </span>
                    <span className="num font-semibold text-green">
                      {formatNumber(odds.reachTargetCount, 0)} /{" "}
                      {formatNumber(odds.replays, 0)} (
                      {formatPct((odds.reachTargetCount / odds.replays) * 100, 1)}
                      )
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1.5 num">
                    +{formatINR(odds.rewardPerShare)} / share · +
                    {formatINR(odds.rewardTotal)} for {autoQtyNum} qty
                  </div>
                </div>
                <div className="bg-[#0d1321] border border-red/30 rounded p-3">
                  <div className="flex items-center justify-between gap-2 text-sm flex-wrap">
                    <span className="text-gray-400 num">
                      Reached {formatINR(autoLevels.stop)}
                    </span>
                    <span className="num font-semibold text-red">
                      {formatNumber(odds.reachStopCount, 0)} /{" "}
                      {formatNumber(odds.replays, 0)} (
                      {formatPct((odds.reachStopCount / odds.replays) * 100, 1)}
                      )
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1.5 num">
                    −{formatINR(odds.riskPerShare)} / share · −
                    {formatINR(odds.riskTotal)} for {autoQtyNum} qty
                  </div>
                </div>
              </div>
              <div className="text-[10px] text-gray-600 leading-relaxed">
                A path can touch both levels — reach counts are independent.
                Tiles above count only which level was hit first.
              </div>
            </div>

            <div className="flex items-center justify-between gap-3 flex-wrap border-t border-gray-800 pt-3">
              <div className="text-sm text-gray-400 num">
                Expected value:{" "}
                <span
                  className={
                    odds.evPerShare >= 0 ? "text-green" : "text-red"
                  }
                >
                  {formatINRSigned(odds.evPerShare)} / share
                </span>{" "}
                ·{" "}
                <span className={odds.evTotal >= 0 ? "text-green" : "text-red"}>
                  {formatINRSigned(odds.evTotal)} for {autoQtyNum} qty
                </span>
              </div>
              <div className="text-[11px] num text-gray-500">
                Levels: entry {formatINR(autoLevels.entry)} · stop{" "}
                {formatINR(autoLevels.stop)} · target{" "}
                {formatINR(autoLevels.target)} (auto from LTP)
              </div>
            </div>

            <div className="flex items-center gap-3 flex-wrap">
              <span
                className={`inline-block px-3 py-2 rounded border text-sm font-bold num ${verdictTone(
                  autoRes.verdict
                )}`}
              >
                {autoRes.verdict}
              </span>
              <span className="text-[11px] text-gray-600 num">
                {formatNumber(autoRes.history.sessions, 0)} sessions pooled ·
                entry bar {String(autoRes.plan?.entry_bar ?? entryBar)} · until{" "}
                {autoMc.until ?? "15:30"}
              </span>
            </div>
          </>
        ) : null}
      </section>
    </div>
  );
}

function Mini({
  label,
  v,
  tone,
}: {
  label: string;
  v: string;
  tone?: "green" | "red";
}) {
  const cls = tone === "green" ? "text-green" : tone === "red" ? "text-red" : "text-white";
  return (
    <div className="bg-[#0d1321] border border-gray-800 rounded p-3">
      <div className="label-caps">{label}</div>
      <div className={`num mt-1 ${cls}`}>{v}</div>
    </div>
  );
}

function HistRow({ k, v, tone }: { k: string; v: string; tone?: "green" | "red" }) {
  const cls = tone === "green" ? "text-green" : tone === "red" ? "text-red" : "text-gray-200";
  return (
    <div className="flex items-center justify-between gap-3 border-b border-gray-800/60 pb-1.5">
      <span className="text-gray-500">{k}</span>
      <span className={`num ${cls}`}>{v}</span>
    </div>
  );
}
