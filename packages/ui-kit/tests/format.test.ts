import { describe, expect, it } from "vitest";
import { formatCurrency, formatNumber, formatWhen, initials, middleTruncate } from "../src/lib/format";

describe("format helpers", () => {
  it("middle truncates and keeps both ends", () => {
    const out = middleTruncate("someone.with.a.long.name@example-company.test", 24);
    expect(out.length).toBe(24);
    expect(out).toContain("…");
    expect(out.startsWith("someone.with")).toBe(true);
    expect(out.endsWith(".test")).toBe(true);
    expect(middleTruncate("short", 24)).toBe("short");
  });
  it("formats numbers and money", () => {
    expect(formatNumber(12345.6)).toBe("12,345.6");
    expect(formatCurrency(1500)).toBe("$1,500");
  });
  it("uses relative time within a week and absolute after", () => {
    const now = new Date("2026-11-22T12:00:00Z");
    expect(formatWhen(new Date("2026-11-22T11:59:40Z"), now)).toBe("just now");
    expect(formatWhen(new Date("2026-11-22T11:30:00Z"), now)).toBe("30 min ago");
    expect(formatWhen(new Date("2026-11-22T07:00:00Z"), now)).toBe("5 h ago");
    expect(formatWhen(new Date("2026-11-20T12:00:00Z"), now)).toBe("2 d ago");
    expect(formatWhen(new Date("2026-11-01T12:00:00Z"), now)).toBe("Nov 1");
    expect(formatWhen(new Date("2025-03-05T12:00:00Z"), now)).toContain("2025");
  });
  it("makes initials", () => {
    expect(initials("Ada Lovelace")).toBe("AL");
    expect(initials("  ")).toBe("?");
    expect(initials("Cher")).toBe("C");
  });
});
