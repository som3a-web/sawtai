import { describe, expect, it } from "vitest";

import { formatCell } from "./format";

describe("formatCell", () => {
  it("formats empty, scalar, and structured values", () => {
    expect(formatCell(null)).toBe("—");
    expect(formatCell(false)).toBe("false");
    expect(formatCell(42)).toBe("42");
    expect(formatCell({ label: "مرحباً" })).toBe('{"label":"مرحباً"}');
  });
});
