"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiGet, apiPost } from "@/lib/api";
import type { ScanFilters, ScanResponse, UniverseResponse } from "@/lib/types";
import { formatINR, formatNumber, formatTime } from "@/lib/format";
import FreshnessBadge from "@/components/FreshnessBadge";

const INTERVALS = ["1m", "5m", "15m", "1d"];

export default function ScannerPage() {
  const [symbolsText, setSymbolsText] = useState("");
  const [minPrice, setMinPrice] = useState("10");
  const [minVolume, setMinVolume] = useState("10000");
  const [interval, setInterval_] = useState("5m");
  const [days, setDays] = useState("30");

  const [universe, setUniverse] = useState<UniverseResponse | null>(null);
  const [result, setResult] = useState<ScanResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<UniverseResponse>("/api/v1/market/universe")
      .then(setUniverse)
      .catch(() => setUniverse(null));
  }, []);

  const runScan = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = symbolsText
        .split(/[,\s]+/)
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean);

      const filters: ScanFilters = {
        min_price: Number(minPrice) || 0,
        min_volume: Number(minVolume) || 0,
        interval,
        days: Number(days) || 30,
      };
      if (list.length) filters.symbols = list;

      const res = await apiPost<ScanResponse>(
        "/api/v1/scanner/scan",
        undefined,
        filters
      );
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [symbolsText, minPrice, minVolume, interval, days]);

  const useUniverse = () => {
    if (universe?.symbols?.length) {
      setSymbolsText(universe.symbols.join(", "));
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">Scanner</h1>
          <p className="text-sm text-gray-500 mt-1">
            Match symbols against technical setups. A scan lists charts matching a
            rule — not stocks to buy.
          </p>
        </div>
        {result ? <FreshnessBadge freshness={result.results[0]?.freshness} source={result.results[0]?.source} /> : null}
      </header>

      <section className="card p-5 space-y-4">
        <div>
          <label className="label-caps block mb-1.5">
            Symbols (comma or space separated)
          </label>
          <textarea
            className="input-dark num min-h-[70px] resize-y"
            placeholder="RELIANCE TCS HDFCBANK"
            value={symbolsText}
            onChange={(e) => setSymbolsText(e.target.value)}
          />
          <div className="flex items-center gap-3 mt-2 flex-wrap">
            <button onClick={useUniverse} className="btn-ghost text-xs" type="button">
              Use full universe ({universe?.count ?? "…"})
            </button>
            <button
              onClick={() => setSymbolsText("")}
              className="text-xs text-gray-500 hover:text-gray-300"
              type="button"
            >
              Clear
            </button>
            <span className="text-[11px] text-gray-600">
              Empty = backend default universe (first 20)
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <label className="label-caps block mb-1.5">Min price (₹)</label>
            <input
              type="number"
              className="input-dark num"
              value={minPrice}
              onChange={(e) => setMinPrice(e.target.value)}
              min={0}
            />
          </div>
          <div>
            <label className="label-caps block mb-1.5">Min volume</label>
            <input
              type="number"
              className="input-dark num"
              value={minVolume}
              onChange={(e) => setMinVolume(e.target.value)}
              min={0}
            />
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
            <label className="label-caps block mb-1.5">Lookback (days)</label>
            <input
              type="number"
              className="input-dark num"
              value={days}
              onChange={(e) => setDays(e.target.value)}
              min={5}
              max={365}
            />
          </div>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <button className="btn-primary" onClick={runScan} disabled={loading}>
            {loading ? "Scanning…" : "Run Scan"}
          </button>
          {loading ? (
            <span className="text-sm text-gray-500">Querying bars & indicators…</span>
          ) : null}
        </div>
      </section>

      {error ? (
        <div className="card p-5 border-red-500/40">
          <div className="text-red-400 font-semibold text-sm mb-1">Scan failed</div>
          <div className="text-gray-400 text-sm num break-all">{error}</div>
        </div>
      ) : null}

      {result ? (
        <section className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Stat label="Scanned" value={formatNumber(result.scanned, 0)} />
            <Stat label="Matched" value={formatNumber(result.matched, 0)} />
            <Stat
              label="Errors"
              value={formatNumber(result.errors?.length ?? 0, 0)}
            />
            <Stat
              label="As of"
              value={result.as_of ? formatTime(result.as_of) : "—"}
            />
          </div>

          <div className="card p-3 text-[12px] text-amber-300/90 border-amber-500/30 bg-amber-500/5">
            {result.note}
          </div>

          {result.errors?.length ? (
            <div className="card p-4">
              <div className="label-caps mb-2">Rejected symbols</div>
              <div className="flex flex-wrap gap-2">
                {result.errors.map((e) => (
                  <span
                    key={e.symbol + e.error}
                    className="text-xs num text-red-400 border border-red-500/30 rounded px-2 py-1"
                    title={e.error}
                  >
                    {e.symbol}: {e.error}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-left">
                  <Th>Symbol</Th>
                  <Th>Price</Th>
                  <Th>Setups</Th>
                  <Th>Reason</Th>
                  <Th>Indicators</Th>
                  <Th>Freshness</Th>
                  <Th>Warnings</Th>
                  <Th>Research</Th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((r) => (
                  <tr
                    key={r.symbol}
                    className="border-b border-gray-800/60 hover:bg-gray-800/30 align-top"
                  >
                    <td className="px-3 py-3">
                      <span className="num font-semibold text-white">
                        {r.symbol}
                      </span>
                    </td>
                    <td className="px-3 py-3 num text-gray-200">
                      {formatINR(r.price)}
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap gap-1.5">
                        {r.setups.length ? (
                          r.setups.map((s) => (
                            <span
                              key={s}
                              className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-accent/15 text-blue-300 border border-accent/40"
                            >
                              {s}
                            </span>
                          ))
                        ) : (
                          <span className="text-xs text-gray-600">none</span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-gray-400 max-w-xs text-[12px] leading-relaxed">
                      {r.reason}
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] num text-gray-400 max-w-[240px]">
                        {Object.entries(r.indicators ?? {}).map(([k, v]) => (
                          <span key={k}>
                            <span className="text-gray-600">{k}</span>{" "}
                            {v === null || v === undefined
                              ? "—"
                              : formatNumber(v, 2)}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <FreshnessBadge freshness={r.freshness} source={r.source} />
                    </td>
                    <td className="px-3 py-3 text-[11px] text-amber-400/90 max-w-[160px]">
                      {r.warnings?.join("; ") || "—"}
                    </td>
                    <td className="px-3 py-3">
                      <Link
                        href={`/research/${encodeURIComponent(r.symbol)}`}
                        className="text-xs text-accent hover:underline whitespace-nowrap"
                      >
                        Research →
                      </Link>
                    </td>
                  </tr>
                ))}
                {!result.results.length ? (
                  <tr>
                    <td
                      colSpan={8}
                      className="px-3 py-8 text-center text-gray-500"
                    >
                      No symbols matched the filters.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
        !loading &&
        !error && (
          <div className="card p-8 text-center text-sm text-gray-600">
            No scan run yet. Set filters and hit Run Scan.
          </div>
        )
      )}
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

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="card p-4">
      <div className="label-caps">{label}</div>
      <div className="num text-xl text-white mt-2">{value}</div>
    </div>
  );
}
