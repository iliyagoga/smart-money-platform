import { afterEach, expect, it, vi } from "vitest";
import { EventSocket } from "./socket";

const auth = vi.hoisted(() => ({ updateToken: vi.fn(), token: "test-token" }));
vi.mock("./auth", () => ({ keycloak: () => auth }));
vi.mock("./api", () => ({ getWebSocketUrl: () => "ws://localhost/ws" }));
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

it("retries token refresh failures and cancels retries on close", async () => {
  vi.useFakeTimers();
  auth.updateToken.mockRejectedValue(new Error("offline"));
  const socket = new EventSocket();
  await expect(socket.connect()).resolves.toBeUndefined();
  await vi.advanceTimersByTimeAsync(1000);
  expect(auth.updateToken).toHaveBeenCalledTimes(2);
  socket.close();
  await vi.advanceTimersByTimeAsync(30000);
  expect(auth.updateToken).toHaveBeenCalledTimes(2);
});

it("ignores malformed messages and delivers valid events", async () => {
  auth.updateToken.mockResolvedValue(false);
  const transport = { readyState: 1, onmessage: vi.fn<(message: { data: string }) => void>(), close: vi.fn() };
  vi.stubGlobal("WebSocket", class { constructor() { return transport; } });
  const socket = new EventSocket();
  const handler = vi.fn();
  socket.subscribe(handler);
  await socket.connect();
  for (const data of ["bad json", "null", "{}"]) transport.onmessage({ data });
  transport.onmessage({ data: JSON.stringify({ event_type: "position.closed" }) });
  expect(handler).toHaveBeenCalledExactlyOnceWith({ event_type: "position.closed" });
  socket.close();
});
