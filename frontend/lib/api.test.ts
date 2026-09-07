import { afterEach, expect, it, vi } from "vitest";
import { api } from "./api";

vi.mock("./auth", () => ({ token: async () => "test-token" }));
afterEach(() => vi.unstubAllGlobals());

it("accepts a successful deletion with no response body", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
  await expect(api("/assets/test", { method: "DELETE" })).resolves.toBeUndefined();
});

it("preserves upstream errors", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Denied", { status: 403 })));
  await expect(api("/assets/test")).rejects.toThrow("403: Denied");
});
