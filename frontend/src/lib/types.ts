// API response types for the Indian Stock Market Intelligence Platform backend.

export type Freshness =
  | "live"
  | "delayed"
  | "synthetic"
  | "historical"
  | "simulated"
  | string;

export type Side = "buy" | "sell";

export interface MarketStatus {
  status: string;
  date: string;
  time: string;
  timezone: string;
  session_open: string;
  session_close: string;
  is_trading_day: boolean;
  holiday: string | null;
  muhurat?: boolean;
}

export interface IndexQuote {
  symbol: string;
  last_price?: number;
  freshness?: string;
  source?: string;
  label?: string;
  error?: string;
}

export interface IndicesResponse {
  indices: IndexQuote[];
  as_of: string;
}

export interface SectorInfo {
  sector: string;
  avg_price: number;
  count: number;
}

export interface SectorsResponse {
  sectors: SectorInfo[];
}

export interface Candle {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface BarsResponse {
  symbol: string;
  interval: string;
  freshness: string;
  source: string;
  as_of: string;
  candles: Candle[];
  count: number;
  exchange?: string;
  staleness?: number | string | null;
}

export interface Quote {
  symbol: string;
  last_price: number;
  volume: number;
  freshness: string;
  source: string;
  exchange?: string;
  ts?: string;
  label?: string;
}

export interface UniverseResponse {
  symbols: string[];
  count: number;
  note?: string;
}

// ---------------------------------------------------------------------------
// Scanner
// ---------------------------------------------------------------------------

export interface ScanFilters {
  symbols?: string[];
  min_price?: number;
  min_volume?: number;
  interval?: string;
  days?: number;
}

export interface ScanResult {
  symbol: string;
  price: number;
  setups: string[];
  indicators: Record<string, number | null>;
  reason: string;
  freshness: string;
  source: string;
  warnings: string[];
}

export interface ScanError {
  symbol: string;
  error: string;
}

export interface ScanResponse {
  scanned: number;
  matched: number;
  results: ScanResult[];
  note: string;
  errors?: ScanError[];
  as_of?: string;
}

// ---------------------------------------------------------------------------
// Trade planner / costs
// ---------------------------------------------------------------------------

export interface CostBreakdown {
  brokerage: number;
  stt: number;
  exchange_charges: number;
  sebi_fees: number;
  stamp_duty: number;
  gst: number;
  slippage_est: number;
  total_est: number;
  as_pct_of_turnover: number;
}

export interface PlanRequest {
  symbol: string;
  side: Side;
  entry_bar: number;
  stop_rule: string;
  target_r: number;
  capital: number;
  risk_pct: number;
}

export interface TradePlan {
  symbol: string;
  side: string;
  entry: number;
  stop: number;
  target: number;
  entry_bar: number;
  entry_time: string;
  risk_per_share: number;
  reward_per_share: number;
  risk_reward: number;
  setup: string;
  stop_rule: string;
  target_r: number;
  invalidation: string;
  max_holding_bars: number;
  costs: CostBreakdown;
  warnings: string[];
  label: string;
}

export interface PlanResponse {
  plan: TradePlan;
  label: string;
  data_label: string;
}

// ---------------------------------------------------------------------------
// Time machine
// ---------------------------------------------------------------------------

export interface TimeMachineRequest {
  symbol: string;
  side: Side;
  entry: number;
  stop: number;
  target: number;
  entry_bar: number;
  replays: number;
  seed: number;
}

export interface TimeMachineMC {
  p_target: number;
  p_stop: number;
  p_neither: number;
  p_green: number;
  median_close: number;
  p5_close?: number;
  p95_close?: number;
  avg_R: number | null;
  r_at_target: number | null;
  bars_left: number;
  seed: number;
  replays?: number;
  count_target?: number;
  count_stop?: number;
  count_close?: number;
  count_reach_target?: number;
  count_reach_stop?: number;
  until?: string;
  window?: number;
  pool_sessions: number;
  pool_from?: string;
  pool_to?: string;
}

export interface TimeMachineHistory {
  sessions: number;
  triggered: number;
  target: number | null;
  stop: number | null;
  close: number | null;
  avg_R: number | null;
  rule?: Record<string, unknown> | null;
  note?: string;
}

export interface TimeMachineResponse {
  plan: Record<string, unknown>;
  mc: TimeMachineMC;
  history: TimeMachineHistory;
  verdict: string;
  verdict_notes: string[];
  note?: string;
  report?: string;
  warnings?: string[];
}

// ---------------------------------------------------------------------------
// Paper trading
// ---------------------------------------------------------------------------

export interface Position {
  symbol: string;
  side: string;
  qty: number;
  avg_price: number;
  unrealized_pnl: number;
  stop: number | null;
  target: number | null;
}

export interface Portfolio {
  cash: number;
  positions: Position[];
  realized_pnl: number;
  total_fees: number;
  trades: number;
  closed_count?: number;
  label: string;
}

export interface OrderRequest {
  symbol: string;
  side: Side;
  qty: number;
  order_type: "market" | "limit";
  price?: number;
}

export interface Order {
  id: string;
  symbol?: string;
  side?: string;
  qty?: number;
  status: string;
  fill_price: number | null;
  fees: number;
  slippage?: number;
  tag?: string;
  limit_price?: number | null;
}

export interface OrderResponse {
  order: Order;
  portfolio: Portfolio;
  label?: string;
}

// ---------------------------------------------------------------------------
// Risk check
// ---------------------------------------------------------------------------

export interface RiskCheckRequest {
  symbol: string;
  side: Side;
  entry: number;
  stop: number;
  target: number;
  shares: number;
  capital: number;
}

export interface RiskCheckItem {
  name: string;
  passed: boolean;
  detail: string;
  level?: string;
}

export interface RiskResponse {
  passed: boolean;
  verdict: "PASS" | "BLOCK";
  checks: RiskCheckItem[];
  reasons: string[];
  fingerprint: string;
  label?: string;
}

// ---------------------------------------------------------------------------
// Backtest
// ---------------------------------------------------------------------------

export interface BacktestRequest {
  symbol: string;
  strategy: string;
  interval: string;
  days: number;
  capital: number;
  risk_pct: number;
}

export interface BacktestTrade {
  entry_time: string;
  exit_time: string;
  entry: number;
  exit: number;
  qty: number;
  side: string;
  pnl: number;
  fees: number;
  r: number;
  reason: string;
}

export interface BacktestResponse {
  symbol: string;
  strategy: string;
  bars: number;
  total_return_pct: number;
  max_drawdown_pct: number;
  sharpe: number;
  win_rate_pct: number;
  profit_factor: number;
  trade_count: number;
  avg_win: number;
  avg_loss: number;
  benchmark_return_pct: number;
  assumptions: string[];
  warnings: string[];
  equity_curve: number[];
  trades: BacktestTrade[];
  data_label: string;
  note: string;
}

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

export interface ClosedTrade {
  symbol: string;
  qty: number;
  avg_price: number;
  pnl: number;
}

export interface PerformanceResponse {
  realized_pnl: number;
  total_fees?: number;
  win_rate_pct: number;
  profit_factor: number;
  trade_count: number;
  closed_count?: number;
  avg_win?: number;
  avg_loss?: number;
  closed_trades: ClosedTrade[];
  label: string;
}
