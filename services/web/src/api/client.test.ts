import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getJson, postJson, setAccessToken } from "./client";

const values = new Map<string, string>();

beforeEach(() => {
  values.clear();
  vi.stubGlobal("sessionStorage", {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  });
  setAccessToken("signed-access-token");
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("API client", () => {
  it("adds session authorization and parses JSON", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ status: "ok" }), { status: 200 }));
    await expect(getJson<{ status: string }>("/health")).resolves.toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith("/health", {
      credentials: "include",
      headers: { Authorization: "Bearer signed-access-token" },
    });
  });

  it("rejects unsuccessful responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(null, { status: 503 }));
    await expect(getJson("/health")).rejects.toThrow("Request failed: 503");
  });

  it("posts JSON with the expected headers", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 202 }));
    await postJson("/drafts", { instruction: "test" });
    expect(fetchMock).toHaveBeenCalledWith("/drafts", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Authorization: "Bearer signed-access-token" },
      body: '{"instruction":"test"}',
    });
  });
});
