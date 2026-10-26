// Trade-plan helpers for the Time Machine page.
// Levels follow the skill default: 0.5% stop distance, 2R target
// (target_r default 2.0 in the planner).

export interface Levels {
  entry: number;
  stop: number;
  target: number;
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
