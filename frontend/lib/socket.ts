import { getWebSocketUrl } from "./api";
import { keycloak } from "./auth";
import type { PlatformEvent } from "./types";

type EventHandler = (event: PlatformEvent) => void;
type StatusHandler = (connected: boolean) => void;

export const allSubscriptionEvents = [
  "candle.*",
  "trade.executed",
  "orderbook.updated",
  "scenario.*",
  "order.*",
  "position.*",
  "trading.config.*",
  "history.*",
];

export class EventSocket {
  private socket?: WebSocket;
  private attempt = 0;
  private closed = false;
  private connecting = false;
  private retryTimer?: ReturnType<typeof setTimeout>;
  private readonly handlers = new Set<EventHandler>();
  private readonly statusHandlers = new Set<StatusHandler>();

  constructor(private readonly subscriptionEvents: string[] = allSubscriptionEvents,
              private readonly symbols: string[] = []) {}

  private reconnect(): void {
    this.statusHandlers.forEach((handler) => handler(false));
    if (this.closed || this.retryTimer !== undefined) return;
    this.retryTimer = setTimeout(() => {
      this.retryTimer = undefined;
      void this.connect();
    }, Math.min(30_000, 1_000 * 2 ** this.attempt++));
  }

  async connect(): Promise<void> {
    if (this.closed || this.connecting || (this.socket && this.socket.readyState < 2)) return;
    this.connecting = true;
    try {
      await keycloak().updateToken(30);
      const accessToken = keycloak().token;
      if (this.closed) return;
      if (!accessToken) { this.reconnect(); return; }

      const socket = new WebSocket(getWebSocketUrl(), ["access_token", accessToken]);
      this.socket = socket;
      socket.onopen = () => {
        this.attempt = 0;
        this.statusHandlers.forEach((handler) => handler(true));
        socket.send(JSON.stringify({ op: "subscribe", events: this.subscriptionEvents, symbols: this.symbols }));
      };
      socket.onmessage = (message) => {
        let event: PlatformEvent;
        try { event = JSON.parse(String(message.data)) as PlatformEvent; }
        catch { return; }
        if (event && typeof event.event_type === "string") this.handlers.forEach((handler) => handler(event));
      };
      socket.onclose = () => this.reconnect();
    } catch {
      this.reconnect();
    } finally {
      this.connecting = false;
    }
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
    clearTimeout(this.retryTimer);
    this.retryTimer = undefined;
    this.socket?.close();
  }
}
