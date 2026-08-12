import { describe, expect, it } from "vitest";

import { initialPage } from "./navigation";

describe("initialPage", () => {
  it.each(["overview", "whatsapp", "voice", "draft", "crisis", "data"])("accepts the %s page", (page) => {
    expect(initialPage(`?page=${page}`)).toBe(page);
  });

  it("falls back for unknown and missing pages", () => {
    expect(initialPage("?page=admin")).toBe("overview");
    expect(initialPage("")).toBe("overview");
  });
});
