import { describe, expect, it } from "vitest";
import {
  formatINR,
  formatINRSigned,
  formatNumber,
  formatPct,
  formatTime,
  formatVolume,
  toChartTime,
} from "../format";

describe("formatINR", () => {
  it("formats with Indian lakh grouping and 2 decimals", () => {
    expect(formatINR(123456.789)).toBe("₹1,23,456.79");
  });

  it("formats zero", () => {
    expect(formatINR(0)).toBe("₹0.00");
  });

  it("formats negatives", () => {
    expect(formatINR(-567.8)).toBe("-₹567.80");
  });

  it("returns em-dash for null/undefined/NaN/non-finite", () => {
    expect(formatINR(null)).toBe("—");
    expect(formatINR(undefined)).toBe("—");
    expect(formatINR(NaN)).toBe("—");
    expect(formatINR(Infinity)).toBe("—");
    expect(formatINR(-Infinity)).toBe("—");
  });

  it("compact mode abbreviates large values", () => {
    expect(formatINR(150000000, true)).toBe("₹15Cr");
  });
});

describe("formatINRSigned", () => {
  it("prefixes + for positives", () => {
    expect(formatINRSigned(1234.5)).toBe("+₹1,234.50");
  });

  it("prefixes - for negatives", () => {
    expect(formatINRSigned(-567.8)).toBe("-₹567.80");
  });

  it("renders zero unsigned", () => {
    expect(formatINRSigned(0)).toBe("₹0.00");
  });

  it("returns em-dash for null/undefined/NaN", () => {
    expect(formatINRSigned(null)).toBe("—");
    expect(formatINRSigned(undefined)).toBe("—");
    expect(formatINRSigned(NaN)).toBe("—");
  });
});

describe("formatPct", () => {
  it("formats with 2 decimals by default", () => {
    expect(formatPct(12.34)).toBe("12.34%");
  });

  it("respects custom digits", () => {
    expect(formatPct(12.345, 1)).toBe("12.3%");
  });

  it("signed mode marks direction but not zero", () => {
    expect(formatPct(5, 2, true)).toBe("+5.00%");
    expect(formatPct(-5, 2, true)).toBe("-5.00%");
    expect(formatPct(0, 2, true)).toBe("0.00%");
  });

  it("returns em-dash for null/undefined/NaN", () => {
    expect(formatPct(null)).toBe("—");
    expect(formatPct(undefined)).toBe("—");
    expect(formatPct(NaN)).toBe("—");
  });
});

describe("formatNumber", () => {
  it("groups with Indian system and 2 decimals", () => {
    expect(formatNumber(1234567.891)).toBe("12,34,567.89");
  });

  it("formats zero", () => {
    expect(formatNumber(0)).toBe("0.00");
  });

  it("formats negatives", () => {
    expect(formatNumber(-1000.5)).toBe("-1,000.50");
  });

  it("returns em-dash for null/undefined/NaN/non-finite", () => {
    expect(formatNumber(null)).toBe("—");
    expect(formatNumber(undefined)).toBe("—");
    expect(formatNumber(NaN)).toBe("—");
    expect(formatNumber(Infinity)).toBe("—");
  });
});

describe("formatVolume", () => {
  it("rounds sub-thousand volumes", () => {
    expect(formatVolume(999)).toBe("999");
    expect(formatVolume(999.6)).toBe("1000");
  });

  it("abbreviates thousands", () => {
    expect(formatVolume(1000)).toBe("1.0K");
    expect(formatVolume(12345)).toBe("12.3K");
  });

  it("abbreviates lakhs", () => {
    expect(formatVolume(1e5)).toBe("1.00L");
    expect(formatVolume(150000)).toBe("1.50L");
  });

  it("abbreviates crores", () => {
    expect(formatVolume(1e7)).toBe("1.00Cr");
    expect(formatVolume(250000000)).toBe("25.00Cr");
  });

  it("returns em-dash for null/undefined/NaN", () => {
    expect(formatVolume(null)).toBe("—");
    expect(formatVolume(undefined)).toBe("—");
    expect(formatVolume(NaN)).toBe("—");
  });
});

describe("formatTime", () => {
  it("formats ISO timestamp in IST display form", () => {
    expect(formatTime("2026-10-24T09:45:00Z")).toBe("24 Oct 2026, 15:15");
  });

  it("returns em-dash for empty input", () => {
    expect(formatTime(null)).toBe("—");
    expect(formatTime(undefined)).toBe("—");
    expect(formatTime("")).toBe("—");
  });

  it("returns raw value for unparseable timestamps", () => {
    expect(formatTime("not-a-date")).toBe("not-a-date");
  });
});

describe("toChartTime", () => {
  it("converts ISO to epoch seconds", () => {
    expect(toChartTime("1970-01-01T00:00:30Z")).toBe(30);
    expect(toChartTime("2026-01-01T00:00:00Z")).toBe(1767225600);
  });
});
