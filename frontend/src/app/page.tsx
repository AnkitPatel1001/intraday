"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet } from "@/lib/api";
import type {
  IndicesResponse,
  MarketStatus,
  SectorsResponse,
  UniverseResponse,
} from "@/lib/types";
import { formatINR, formatTime } from "@/lib/format";
import FreshnessBadge from "@/components/FreshnessBadge";
import MarketStatusBadge from "@/components/MarketStatusBadge";

interface SectorCard {
  sector: string;
  avg_price: number;
  count: number;
  freshness?: string;
}

export default function DashboardPage() {
  const [status, setStatus] = useState<MarketStatus | null>(null);
  const [indices, setIndices] = useState<IndicesResponse | null>(null);
  const [sectors, setSectors] = useState<SectorCard[]>([]);
  const [universe, setUniverse] = useState<UniverseResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [st, ix, sec, uni] = await Promise.all([
        apiGet<MarketStatus>("/api/v1/market/status"),
        apiGet<IndicesResponse>("/api/v1/market/indices"),
        apiGet<SectorsResponse>("/api/v1/market/sectors").catch(() => ({
          sectors: [] as never[],
        })),
        apiGet<UniverseResponse>("/api/v1/market/universe").catch(
          () => ({ symbols: [], count: 0 } as UniverseResponse)
        ),
      ]);
      setStatus(st);
      setIndices(ix);
      setSectors(sec.sectors ?? []);
      setUniverse(uni);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const indexList = indices?.indices ?? [];
  const freshest = indexList.find((i) => i.freshness)?.freshness;
  const freshestSource = indexList.find((i) => i.source)?.source;

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">
            Market overview · NSE session ·{" "}
            {indices?.as_of ? `as of ${formatTime(indices.as_of)}` : "loading…"}
          </p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          {freshest ? (
            <FreshnessBadge freshness={freshest} source={freshestSource} />
          ) : null}
          <MarketStatusBadge status={status} />
        </div>
      </header>

      {loading ? (
        <div className="card p-8 text-center text-gray-500 text-sm">
          Loading market data…
        </div>
      ) : null}

      {error ? (
        <div className="card p-6 border-red-500/40">
          <div className="text-red-400 font-semibold text-sm mb-2">
            Failed to load market data
          </div>
          <div className="text-gray-400 text-sm num break-all">{error}</div>
          <button onClick={load} className="btn-primary mt-4">
            Retry
          </button>
        </div>
      ) : null}

      {!loading && !error ? (
        <>
          <section>
            <div className="label-caps mb-3">Indices</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {indexList.map((idx) => (
                <div key={idx.symbol} className="card p-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-white text-sm">
                      {idx.symbol}
                    </span>
                    {idx.freshness ? (
                      <FreshnessBadge freshness={idx.freshness} source={idx.source} />
                    ) : null}
                  </div>
                  <div className="num text-2xl text-white mt-3">
                    {idx.error ? (
                      <span className="text-red-400 text-sm">{idx.error}</span>
                    ) : (
                      formatINR(idx.last_price)
                    )}
                  </div>
                  <div className="text-[11px] text-gray-500 mt-1 num">
                    source: {idx.source ?? "—"}
                  </div>
                </div>
              ))}
              {!indexList.length ? (
                <div className="card p-4 text-sm text-gray-500 col-span-full">
                  No index data returned.
                </div>
              ) : null}
            </div>
          </section>

          <section>
            <div className="label-caps mb-3">Sectors</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {sectors.map((s) => (
                <div key={s.sector} className="card p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-300">
                      {s.sector}
                    </span>
                    <span className="text-[11px] text-gray-500 num">
                      {s.count} stocks
                    </span>
                  </div>
                  <div className="num text-xl text-white mt-2">
                    {formatINR(s.avg_price)}
                  </div>
                  <div className="text-[11px] text-gray-500 mt-1">
                    avg price · demo universe
                  </div>
                </div>
              ))}
              {!sectors.length ? (
                <div className="card p-4 text-sm text-gray-500 col-span-full">
                  No sector data available.
                </div>
              ) : null}
            </div>
          </section>

          <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="card p-4">
              <div className="label-caps">Session</div>
              <div className="mt-3 space-y-1.5 text-sm">
                <Row k="Date" v={status?.date ?? "—"} />
                <Row k="Open" v={status?.session_open ?? "—"} />
                <Row k="Close" v={status?.session_close ?? "—"} />
                <Row k="Timezone" v={status?.timezone ?? "—"} />
                <Row
                  k="Trading day"
                  v={status?.is_trading_day ? "Yes" : "No"}
                  tone={status?.is_trading_day ? "green" : "red"}
                />
                <Row
                  k="Holiday"
                  v={status?.holiday ?? "none"}
                  tone={status?.holiday ? "amber" : undefined}
                />
              </div>
            </div>

            <div className="card p-4">
              <div className="label-caps">Universe</div>
              <div className="num text-3xl text-white mt-3">
                {universe?.count ?? 0}
              </div>
              <div className="text-sm text-gray-500 mt-1">
                symbols available to scan / research
              </div>
              <div className="text-[11px] text-gray-600 mt-3 leading-relaxed">
                {universe?.note ?? "Demo universe."}
              </div>
              <div className="mt-4 flex gap-2 flex-wrap">
                <Link href="/scanner" className="btn-primary text-sm">
                  Open Scanner
                </Link>
                <Link href="/backtest" className="btn-ghost text-sm">
                  Run Backtest
                </Link>
              </div>
            </div>

            <div className="card p-4">
              <div className="label-caps">Quick research</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {(universe?.symbols ?? []).slice(0, 12).map((sym) => (
                  <Link
                    key={sym}
                    href={`/research/${encodeURIComponent(sym)}`}
                    className="px-2 py-1 text-xs num border border-gray-800 rounded hover:border-accent hover:text-white text-gray-400 transition-colors"
                  >
                    {sym}
                  </Link>
                ))}
              </div>
              <div className="text-[11px] text-gray-600 mt-4">
                Prices shown are {freshest ?? "simulated"} data from{" "}
                {freshestSource ?? "demo provider"}.
              </div>
            </div>
          </section>

          <footer className="text-[11px] text-gray-600 border-t border-gray-800 pt-4">
            This desk runs on simulated feeds. Simulated data, not investment
            advice.
          </footer>
        </>
      ) : null}
    </div>
  );
}

function Row({
  k,
  v,
  tone,
}: {
  k: string;
  v: string;
  tone?: "green" | "red" | "amber";
}) {
  const color =
    tone === "green"
      ? "text-green"
      : tone === "red"
      ? "text-red"
      : tone === "amber"
      ? "text-amber-400"
      : "text-gray-200";
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-gray-500">{k}</span>
      <span className={`num ${color}`}>{v}</span>
    </div>
  );
}
