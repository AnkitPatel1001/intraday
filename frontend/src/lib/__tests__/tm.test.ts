import { describe, expect, it } from "vitest";
import { autoOdds, deriveLevels, validLevels } from "../tm";
import type { TimeMachineMC } from "../types";

function mc(partial: Partial<TimeMachineMC>): TimeMachineMC {
  return {
    p_target: 0,
    p_stop: 0,
    p_neither: 0,
    p_green: 0,
    median_close: 0,
    avg_R: null,
    r_at_target: null,
    bars_left: 70,
    seed: 19,
    pool_sessions: 38,
    ...partial,
  };
}

describe("deriveLevels", () => {
  it("buy: stop 0.5% below, target 2R above the live price", () => {
    const lv = deriveLevels(579.5, "buy");
    expect(lv.entry).toBe(579.5);
    expect(lv.stop).toBe(576.6); // 2.9 risk (0.5%), rounded to paise
    expect(lv.target).toBe(585.3); // 2R = 5.8
    expect(validLevels(String(lv.entry), String(lv.stop), String(lv.target))).toBe(true);
  });

  it("sell: stop above, target below the live price", () => {
    const lv = deriveLevels(579.5, "sell");
    expect(lv.entry).toBe(579.5);
    expect(lv.stop).toBe(582.4);
    expect(lv.target).toBe(573.7);
    expect(validLevels(String(lv.entry), String(lv.stop), String(lv.target))).toBe(true);
  });

  it("keeps a minimum 0.01 stop distance on tiny prices", () => {
    const lv = deriveLevels(0.5, "buy");
    expect(lv.entry).toBe(0.5);
    expect(lv.stop).toBe(0.49);
    expect(lv.target).toBe(0.52);
  });

  it("rejects non-positive prices", () => {
    expect(() => deriveLevels(Number.NaN, "buy")).toThrow();
    expect(() => deriveLevels(-1, "buy")).toThrow();
  });
});

describe("validLevels", () => {
  it("accepts buy ordering stop < entry < target", () => {
    expect(validLevels("2500", "2475", "2550")).toBe(true);
  });

  it("accepts sell ordering target < entry < stop", () => {
    expect(validLevels("2500", "2525", "2475")).toBe(true);
  });

  it("rejects buy with stop above entry", () => {
    expect(validLevels("2500", "2525", "2550")).toBe(false);
  });

  it("rejects empty or zero values", () => {
    expect(validLevels("", "1", "2")).toBe(false);
    expect(validLevels("0", "1", "2")).toBe(false);
  });
});

describe("autoOdds", () => {
  const buyLevels = { entry: 100, stop: 99, target: 102 };

  it("buy: exact counts, per-share and total ₹ amounts, EV", () => {
    const o = autoOdds(
      mc({
        replays: 10000,
        count_target: 3000,
        count_stop: 2500,
        count_close: 4500,
        count_reach_target: 8000,
        count_reach_stop: 6500,
        p_target: 0.3,
        p_stop: 0.25,
        p_neither: 0.45,
      }),
      buyLevels,
      "buy",
      10
    );
    expect(o.targetCount).toBe(3000);
    expect(o.stopCount).toBe(2500);
    expect(o.neitherCount).toBe(4500);
    expect(o.reachTargetCount).toBe(8000); // any touch, overlaps allowed
    expect(o.reachStopCount).toBe(6500);
    expect(o.reachTargetCount).toBeGreaterThanOrEqual(o.targetCount);
    expect(o.reachStopCount).toBeGreaterThanOrEqual(o.stopCount);
    expect(o.rewardPerShare).toBe(2); // target - entry
    expect(o.riskPerShare).toBe(1); // entry - stop
    expect(o.rewardTotal).toBe(20); // × 10 qty
    expect(o.riskTotal).toBe(10);
    expect(o.evPerShare).toBe(0.35); // 0.3×2 − 0.25×1
    expect(o.evTotal).toBe(3.5);
  });

  it("sell: reward = entry−target, risk = stop−entry", () => {
    const o = autoOdds(
      mc({
        replays: 10000,
        count_target: 4000,
        count_stop: 2000,
        count_close: 4000,
        p_target: 0.4,
        p_stop: 0.2,
        p_neither: 0.4,
      }),
      { entry: 100, stop: 101, target: 98 },
      "sell",
      5
    );
    expect(o.rewardPerShare).toBe(2); // entry - target
    expect(o.riskPerShare).toBe(1); // stop - entry
    expect(o.rewardTotal).toBe(10);
    expect(o.riskTotal).toBe(5);
    expect(o.evPerShare).toBe(0.6); // 0.4×2 − 0.2×1
  });

  it("falls back to p × replays when raw counts are missing", () => {
    const o = autoOdds(
      mc({ p_target: 0.3333, p_stop: 0.25, p_neither: 0.4167 }),
      buyLevels,
      "buy",
      1
    );
    expect(o.replays).toBe(10000);
    expect(o.targetCount).toBe(3333);
    expect(o.stopCount).toBe(2500);
    expect(o.neitherCount).toBe(4167);
    // reach missing -> conservative first-hit lower bound
    expect(o.reachTargetCount).toBe(3333);
    expect(o.reachStopCount).toBe(2500);
  });

  it("treats non-positive qty as 1", () => {
    const o = autoOdds(
      mc({ p_target: 1, p_stop: 0, p_neither: 0, count_target: 10 }),
      buyLevels,
      "buy",
      0
    );
    expect(o.rewardTotal).toBe(2);
    expect(o.evTotal).toBe(2);
  });
});
