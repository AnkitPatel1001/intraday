"use client";

const STYLES: Record<string, string> = {
  synthetic: "bg-amber-500/15 text-amber-300 border-amber-500/50",
  delayed: "bg-orange-500/15 text-orange-300 border-orange-500/50",
  live: "bg-green-500/15 text-green-300 border-green-500/50",
  historical: "bg-blue-500/15 text-blue-300 border-blue-500/50",
  simulated: "bg-purple-500/15 text-purple-300 border-purple-500/50",
};

const DEFAULT_STYLE = "bg-gray-500/15 text-gray-300 border-gray-500/50";

interface Props {
  freshness?: string | null;
  source?: string | null;
  className?: string;
}

export default function FreshnessBadge({ freshness, source, className }: Props) {
  if (!freshness) {
    return (
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded border ${DEFAULT_STYLE} ${
          className ?? ""
        }`}
      >
        unknown
      </span>
    );
  }

  const key = freshness.toLowerCase();
  const style = STYLES[key] ?? DEFAULT_STYLE;

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded border ${style} ${
        className ?? ""
      }`}
      title={source ? `source: ${source}` : undefined}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${
          key === "live"
            ? "bg-green-400 animate-pulse"
            : key === "synthetic" || key === "simulated"
            ? "bg-amber-400"
            : key === "delayed"
            ? "bg-orange-400"
            : "bg-blue-400"
        }`}
      />
      {freshness}
      {source ? <span className="opacity-60 normal-case">· {source}</span> : null}
    </span>
  );
}
