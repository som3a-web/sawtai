import { describe, expect, it } from "vitest";

import { parseSseBlock } from "./sse";

describe("parseSseBlock", () => {
  it("parses named JSON events", () => {
    expect(parseSseBlock('event: token\ndata: {"delta":"مرحبا "}')).toEqual({
      name: "token",
      data: { delta: "مرحبا " },
    });
  });

  it("joins multiline data and defaults the event name", () => {
    expect(parseSseBlock('data: {"ok":\ndata: true}')).toEqual({
      name: "message",
      data: { ok: true },
    });
  });

  it("ignores blocks without data", () => {
    expect(parseSseBlock("event: heartbeat")).toBeNull();
  });
});
