import { describe, expect, it } from "vitest";
import { formatMoney, formatSignedMoney } from "./formatters";

describe("money formatters", () => {
  it("formats a missing monetary value as zero", () => {
    expect(formatMoney()).toBe("0,00");
  });

  it("adds a plus sign to positive values", () => {
    expect(formatSignedMoney(12.5)).toBe("+12,50");
  });

  it("keeps the minus sign for negative values", () => {
    expect(formatSignedMoney(-12.5)).toBe("-12,50");
  });
});
