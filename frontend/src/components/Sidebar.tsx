"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItem {
  href: string;
  label: string;
  hint?: string;
}

const NAV: NavItem[] = [
  { href: "/", label: "Dashboard" },
  { href: "/scanner", label: "Scanner" },
  { href: "/research/RELIANCE", label: "Research" },
  { href: "/calculator", label: "Calculator" },
  { href: "/timemachine", label: "Time Machine" },
  { href: "/paper", label: "Paper Trading" },
  { href: "/backtest", label: "Backtest" },
  { href: "/risk", label: "Risk" },
];

export default function Sidebar() {
  const pathname = usePathname();

  const isActive = (href: string): boolean => {
    if (href === "/") return pathname === "/";
    if (href.startsWith("/research")) return pathname.startsWith("/research");
    return pathname === href;
  };

  return (
    <aside className="w-56 shrink-0 border-r border-gray-800 bg-[#0b111d] min-h-screen flex flex-col sticky top-0">
      <div className="px-4 py-5 border-b border-gray-800">
        <div className="text-accent font-bold text-sm tracking-widest">
          MARKET INTEL
        </div>
        <div className="text-[11px] text-gray-500 mt-1">
          Indian equities · research desk
        </div>
      </div>

      <nav className="flex-1 py-3">
        {NAV.map((item) => {
          const active = isActive(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`block px-4 py-2.5 text-sm transition-colors border-l-2 ${
                active
                  ? "border-accent bg-blue-500/10 text-white"
                  : "border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-800/40"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="px-4 py-4 border-t border-gray-800 space-y-2">
        <div className="inline-block px-2 py-1 text-[10px] font-bold tracking-wider bg-purple-500/20 text-purple-300 border border-purple-500/40 rounded">
          PAPER TRADING
        </div>
        <div className="inline-block px-2 py-1 text-[10px] font-bold tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded">
          SIMULATED DATA
        </div>
        <p className="text-[10px] leading-relaxed text-gray-600">
          Research tooling only. Not investment advice.
        </p>
      </div>
    </aside>
  );
}
