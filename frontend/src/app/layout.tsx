import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "Indian Stock Market Intelligence Platform",
  description:
    "Research, scanner, backtesting and paper trading desk for Indian equities. Simulated data — not investment advice.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-bg text-gray-200 antialiased">
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 min-w-0">
            <div className="border-b border-gray-800 bg-[#0b111d] px-6 py-2.5 flex items-center gap-3 flex-wrap">
              <span className="px-2 py-0.5 text-[10px] font-bold tracking-wider bg-purple-500/20 text-purple-300 border border-purple-500/40 rounded">
                PAPER TRADING
              </span>
              <span className="px-2 py-0.5 text-[10px] font-bold tracking-wider bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded">
                SIMULATED DATA
              </span>
              <span className="text-[11px] text-gray-500">
                Research tooling — not a recommendation to buy or sell.
              </span>
            </div>
            <div className="p-6">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
