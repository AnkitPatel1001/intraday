import { describe, expect, it } from "vitest";
import { deriveLevels, validLevels } from "../tm";

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
