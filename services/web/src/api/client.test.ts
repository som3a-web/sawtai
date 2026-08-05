import { afterEach, describe, expect, it, vi } from "vitest";

import { getJson, postJson } from "./client";

afterEach(() => vi.restoreAllMocks());

describe("API client", () => {
  it("adds prototype authorization and parses JSON", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
    );

    await expect(getJson<{ status: string }>("/health")).resolves.toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith("/health", {
      headers: { Authorization: "Bearer sawtai-demo-token" },
    });
  });

  it("rejects unsuccessful responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 503 }));
    await expect(getJson("/health")).rejects.toThrow("Request failed: 503");
  });

  it("posts JSON with the expected headers", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 202 }));
    await postJson("/drafts", { instruction: "test" });
    expect(fetchMock).toHaveBeenCalledWith("/drafts", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer sawtai-demo-token",
      },
      body: '{"instruction":"test"}',
    });
  });
});
