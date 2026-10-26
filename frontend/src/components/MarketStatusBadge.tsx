"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import type { MarketStatus } from "@/lib/types";

interface Props {
  status?: MarketStatus | null;
  className?: string;
}

function deriveOpen(status: MarketStatus | null | undefined): boolean {
  if (!status) return false;
  const s = (status.status || "").toLowerCase();
  if (s.includes("open")) return true;
  if (s.includes("close") || s.includes("closed")) return false;
  return status.session_open <= status.time && status.time < status.session_close;
}

export default function MarketStatusBadge({ status: incoming, className }: Props) {
  const [status, setStatus] = useState<MarketStatus | null>(incoming ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (incoming) {
      setStatus(incoming);
      return;
    }
    let cancelled = false;
    const load = () =>
      apiGet<MarketStatus>("/api/v1/market/status")
        .then((data) => {
          if (!cancelled) {
            setStatus(data);
            setError(null);
          }
        })
        .catch((err: Error) => {
          if (!cancelled) setError(err.message);
        });
    load();
    const id = setInterval(load, 30_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [incoming]);

  if (error && !status) {
    return (
      <span
        className={`inline-flex items-center gap-2 px-3 py-1.5 rounded border text-xs font-bold bg-gray-500/15 text-gray-300 border-gray-500/50 ${
          className ?? ""
        }`}
      >
        STATUS UNAVAILABLE
      </span>
    );
  }

  if (!status) {
    return (
      <span
        className={`inline-flex items-center gap-2 px-3 py-1.5 rounded border text-xs font-bold bg-gray-500/15 text-gray-400 border-gray-500/50 ${
          className ?? ""
        }`}
      >
        CHECKING…
      </span>
    );
  }

  const open = deriveOpen(status);
  const tradingDay = status.is_trading_day;

  return (
    <div
      className={`inline-flex items-center gap-3 px-3 py-1.5 rounded border text-xs font-bold ${
        open
          ? "bg-green-500/15 text-green-300 border-green-500/50"
          : "bg-red-500/15 text-red-300 border-red-500/50"
      } ${className ?? ""}`}
    >
      <span className="flex items-center gap-2">
        <span
          className={`w-2 h-2 rounded-full ${
            open ? "bg-green-400 animate-pulse" : "bg-red-400"
          }`}
        />
        {open ? "MARKET OPEN" : "MARKET CLOSED"}
      </span>
      <span className="num text-gray-300 font-normal">
        {status.time} {status.timezone?.replace("Asia/", "")}
      </span>
      <span className="text-gray-400 font-normal">
        {status.session_open}–{status.session_close}
      </span>
      {!tradingDay ? (
        <span className="text-amber-300 font-normal">
          {status.holiday ? `Holiday: ${status.holiday}` : "Non-trading day"}
        </span>
      ) : null}
    </div>
  );
}
