"use client";

import { useState } from "react";
import { apiPost } from "@/lib/api";
import type { RiskCheckRequest, RiskResponse } from "@/lib/types";
import { formatINR, formatNumber } from "@/lib/format";

export default function RiskPage() {
  const [symbol, setSymbol] = useState("RELIANCE");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [entry, setEntry] = useState("2500");
  const [stop, setStop] = useState("2475");
  const [target, setTarget] = useState("2550");
  const [shares, setShares] = useState("100");
  const [capital, setCapital] = useState("500000");

  const [result, setResult] = useState<RiskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const check = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const body: RiskCheckRequest = {
        symbol: symbol.toUpperCase().trim(),
        side,
        entry: Number(entry),
        stop: Number(stop),
        target: Number(target),
        shares: Number(shares) || 0,
        capital: Number(capital) || 0,
      };
      if (!body.entry || !body.stop || !body.target) {
        throw new Error("entry, stop and target are required");
      }
      const res = await apiPost<RiskResponse>("/api/v1/risk/check", body);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const passed = result?.checks?.filter((c) => c.passed).length ?? 0;
  const totalChecks = result?.checks?.length ?? 0;

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">Risk Check</h1>
          <p className="text-sm text-gray-500 mt-1">
            Rule verification before entry: position size, risk budget, stop
            presence, reward:risk and daily loss limits.
          </p>
        </div>
        <span className="px-2 py-1 text-[10px] font-bold tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded">
          SIMULATED DATA
        </span>
      </header>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <form onSubmit={check} className="card p-5 space-y-4 h-fit">
          <div className="label-caps">Trade inputs</div>
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="label-caps block mb-1.5">Symbol</label>
              <input
                className="input-dark num uppercase"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                required
              />
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
              <label className="label-caps block mb-1.5">Shares</label>
              <input
                type="number"
                min={0}
                className="input-dark num"
                value={shares}
                onChange={(e) => setShares(e.target.value)}
              />
            </div>
            <div>
              <label className="label-caps block mb-1.5">Entry (₹)</label>
              <input
                type="number"
                step="0.05"
                className="input-dark num"
                value={entry}
                onChange={(e) => setEntry(e.target.value)}
              />
            </div>
            <div>
              <label className="label-caps block mb-1.5">Stop (₹)</label>
              <input
                type="number"
                step="0.05"
                className="input-dark num"
                value={stop}
                onChange={(e) => setStop(e.target.value)}
              />
            </div>
            <div>
              <label className="label-caps block mb-1.5">Target (₹)</label>
              <input
                type="number"
                step="0.05"
                className="input-dark num"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
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
          </div>

          <button className="btn-primary w-full" disabled={loading}>
            {loading ? "Checking rules…" : "Run risk check"}
          </button>

          <div className="text-[11px] text-gray-600 leading-relaxed">
            Uses server-side default limits (risk per trade, max positions, min
            R:R, daily loss cap). A PASS is rules compliance, not a recommendation.
          </div>

          {error ? (
            <div className="text-xs text-red-400 num break-all border border-red-500/30 rounded p-2 bg-red-500/5">
              {error}
            </div>
          ) : null}
        </form>

        <section className="xl:col-span-2 space-y-6">
          {!result && !loading ? (
            <div className="card p-10 text-center text-sm text-gray-600">
              Submit a trade to see PASS/BLOCK verdict with per-rule detail.
            </div>
          ) : null}

          {loading ? (
            <div className="card p-10 text-center text-sm text-gray-500">
              Running risk rules…
            </div>
          ) : null}

          {result ? (
            <>
              <div
                className={`card p-6 border-2 ${
                  result.passed
                    ? "border-green/60 bg-green/5"
                    : "border-red/60 bg-red/5"
                }`}
              >
                <div className="flex items-center gap-4 flex-wrap justify-between">
                  <div className="flex items-center gap-4">
                    <div
                      className={`text-3xl font-black num tracking-wider ${
                        result.passed ? "text-green" : "text-red"
                      }`}
                    >
                      {result.verdict}
                    </div>
                    <div className="text-sm text-gray-400">
                      {passed}/{totalChecks} checks passed
                      {result.reasons.length
                        ? ` · ${result.reasons.length} blocking reason${
                            result.reasons.length > 1 ? "s" : ""
                          }`
                        : ""}
                    </div>
                  </div>
                  <div className="text-[11px] num text-gray-500">
                    fingerprint {result.fingerprint}
                  </div>
                </div>

                <div className="mt-4 h-3 bg-[#0d1321] rounded overflow-hidden border border-gray-800">
                  <div
                    className={`h-full transition-all duration-700 ${
                      result.passed ? "bg-green" : "bg-red"
                    }`}
                    style={{
                      width: `${
                        totalChecks ? (passed / totalChecks) * 100 : 0
                      }%`,
                    }}
                  />
                </div>

                {result.reasons.length ? (
                  <ul className="mt-4 space-y-1.5 text-sm text-red-300 list-disc pl-5">
                    {result.reasons.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                ) : (
                  <div className="mt-4 text-sm text-green">
                    All rules satisfied for this trade.
                  </div>
                )}
              </div>

              <div className="card">
                <div className="px-5 py-3 border-b border-gray-800">
                  <span className="label-caps">Rule detail</span>
                </div>
                <ul>
                  {result.checks.map((c, i) => (
                    <li
                      key={`${c.name}-${i}`}
                      className="px-5 py-3 border-b border-gray-800/60 flex items-start gap-4"
                    >
                      <span
                        className={`mt-0.5 w-5 h-5 shrink-0 rounded-full flex items-center justify-center text-[11px] font-bold ${
                          c.passed
                            ? "bg-green/20 text-green border border-green/50"
                            : "bg-red/20 text-red border border-red/50"
                        }`}
                      >
                        {c.passed ? "✓" : "✕"}
                      </span>
                      <span className="min-w-0">
                        <span className="block text-sm text-gray-200 font-medium">
                          {c.name}
                        </span>
                        <span className="block text-[12px] text-gray-500 num">
                          {c.detail}
                        </span>
                      </span>
                      <span
                        className={`ml-auto text-[10px] font-bold tracking-wider ${
                          c.passed ? "text-green" : "text-red"
                        }`}
                      >
                        {c.passed ? "PASS" : "FAIL"}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="card p-5 grid grid-cols-2 md:grid-cols-4 gap-4">
                <Field label="Entry" value={formatINR(Number(entry))} />
                <Field label="Stop" value={formatINR(Number(stop))} tone="red" />
                <Field label="Target" value={formatINR(Number(target))} tone="green" />
                <Field
                  label="Risk if stopped"
                  value={formatINR(
                    Math.abs(Number(entry) - Number(stop)) * (Number(shares) || 0)
                  )}
                />
                <Field
                  label="Reward if target"
                  value={formatINR(
                    Math.abs(Number(target) - Number(entry)) * (Number(shares) || 0)
                  )}
                  tone="green"
                />
                <Field
                  label="Position value"
                  value={formatINR(Number(entry) * (Number(shares) || 0))}
                />
                <Field
                  label="R:R"
                  value={
                    Math.abs(Number(entry) - Number(stop)) > 0
                      ? `1 : ${formatNumber(
                          Math.abs(Number(target) - Number(entry)) /
                            Math.abs(Number(entry) - Number(stop)),
                          2
                        )}`
                      : "—"
                  }
                />
                <Field label="Capital" value={formatINR(Number(capital))} />
              </div>

              {result.label ? (
                <div className="text-[11px] text-gray-600">{result.label}</div>
              ) : null}
            </>
          ) : null}
        </section>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "green" | "red";
}) {
  const cls = tone === "green" ? "text-green" : tone === "red" ? "text-red" : "text-white";
  return (
    <div className="bg-[#0d1321] border border-gray-800 rounded p-3">
      <div className="label-caps">{label}</div>
      <div className={`num mt-1 ${cls}`}>{value}</div>
    </div>
  );
}
