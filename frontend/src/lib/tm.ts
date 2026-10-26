// Trade-plan helpers for the Time Machine page.
// Levels follow the skill default: 0.5% stop distance, 2R target
// (target_r default 2.0 in the planner).

import type { TimeMachineMC } from "./types";

export interface Levels {
  entry: number;
  stop: number;
  target: number;
}

export interface AutoOdds {
  replays: number;
  targetCount: number;
  stopCount: number;
  neitherCount: number;
  reachTargetCount: number; // paths that touched target at any point
  reachStopCount: number; // paths that touched stop at any point
  rewardPerShare: number; // ₹ gained if target hit
  riskPerShare: number; // ₹ lost if stop hit
  rewardTotal: number; // × qty
  riskTotal: number;
  evPerShare: number; // p(target)·reward − p(stop)·risk
  evTotal: number;
}

function round2(x: number): number {
  return Math.round(x * 100) / 100;
}

export function deriveLevels(ltp: number, side: "buy" | "sell"): Levels {
  if (!Number.isFinite(ltp) || ltp <= 0) {
    throw new Error(`live price must be a positive number, got ${ltp}`);
  }
  const entry = round2(ltp);
  let risk = round2(entry * 0.005);
  if (risk < 0.01) risk = 0.01;
  const reward = round2(risk * 2);
  return side === "buy"
    ? { entry, stop: round2(entry - risk), target: round2(entry + reward) }
    : { entry, stop: round2(entry + risk), target: round2(entry - reward) };
}

export function validLevels(entry: string, stop: string, target: string): boolean {
  const e = Number(entry);
  const s = Number(stop);
  const t = Number(target);
  if (!e || !s || !t) return false;
  // buy: stop < entry < target; sell: target < entry < stop
  if (s < e && e < t) return true;
  if (t < e && e < s) return true;
  return false;
}

// Exact hit counts + ₹ amounts from a Time Machine Monte Carlo result.
// Backend returns raw counts (count_target/stop/close); falls back to
// p × replays for older responses.
export function autoOdds(
  mc: TimeMachineMC,
  levels: Levels,
  side: "buy" | "sell",
  qty: number
): AutoOdds {
  const replays = mc.replays ?? 10000;
  const targetCount =
    mc.count_target ?? Math.round(mc.p_target * replays);
  const stopCount = mc.count_stop ?? Math.round(mc.p_stop * replays);
  const neitherCount = mc.count_close ?? Math.round(mc.p_neither * replays);
  // Reach = any touch; falls back to first-hit counts (a lower bound).
  const reachTargetCount = mc.count_reach_target ?? targetCount;
  const reachStopCount = mc.count_reach_stop ?? stopCount;

  const rawReward =
    side === "buy" ? levels.target - levels.entry : levels.entry - levels.target;
  const rawRisk =
    side === "buy" ? levels.entry - levels.stop : levels.stop - levels.entry;
  const rewardPerShare = round2(Math.max(0, rawReward));
  const riskPerShare = round2(Math.max(0, rawRisk));

  const q = Number.isFinite(qty) && qty > 0 ? qty : 1;
  const evPerShare = round2(
    mc.p_target * rewardPerShare - mc.p_stop * riskPerShare
  );

  return {
    replays,
    targetCount,
    stopCount,
    neitherCount,
    reachTargetCount,
    reachStopCount,
    rewardPerShare,
    riskPerShare,
    rewardTotal: round2(rewardPerShare * q),
    riskTotal: round2(riskPerShare * q),
    evPerShare,
    evTotal: round2(evPerShare * q),
  };
}
