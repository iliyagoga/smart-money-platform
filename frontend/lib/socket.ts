import { getWebSocketUrl } from "./api";
import { keycloak } from "./auth";
import type { PlatformEvent } from "./types";

type EventHandler = (event: PlatformEvent) => void;
type StatusHandler = (connected: boolean) => void;

export const allSubscriptionEvents = [
  "candle.*",
  "trade.executed",
  "orderbook.updated",
  "smc.*",
  "scenario.*",
  "position.*",
  "model.*",
  "bandit.*",
];

export class EventSocket {
  private socket?: WebSocket;
  private attempt = 0;
  private closed = false;
  private readonly handlers = new Set<EventHandler>();
  private readonly statusHandlers = new Set<StatusHandler>();

  constructor(private readonly subscriptionEvents: string[] = allSubscriptionEvents) {}

  async connect(): Promise<void> {
    await keycloak().updateToken(30);
    const accessToken = keycloak().token;
    if (this.closed || !accessToken) return;

    this.socket = new WebSocket(getWebSocketUrl(), ["access_token", accessToken]);
    this.socket.onopen = () => {
      this.attempt = 0;
      this.statusHandlers.forEach((handler) => handler(true));
      this.socket?.send(JSON.stringify({ op: "subscribe", events: this.subscriptionEvents }));
    };
    this.socket.onmessage = (message) => {
      const event = JSON.parse(String(message.data)) as PlatformEvent;
      if (event.event_type) this.handlers.forEach((handler) => handler(event));
    };
    this.socket.onclose = () => {
      this.statusHandlers.forEach((handler) => handler(false));
      if (!this.closed) window.setTimeout(() => void this.connect(), Math.min(30_000, 1_000 * 2 ** this.attempt++));
    };
  }

  subscribe(handler: EventHandler): () => boolean {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  subscribeStatus(handler: StatusHandler): () => boolean {
    this.statusHandlers.add(handler);
    return () => this.statusHandlers.delete(handler);
  }

  close(): void {
    this.closed = true;
    this.socket?.close();
  }
}
