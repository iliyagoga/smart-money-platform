import { getWebSocketUrl } from "./api";
import { keycloak } from "./auth";
import type { PlatformEvent } from "./types";

type EventHandler = (event: PlatformEvent) => void;

const subscriptionEvents = ["candle.*", "smc.*", "scenario.*", "position.*", "model.*", "bandit.*"];

export class EventSocket {
  private socket?: WebSocket;
  private attempt = 0;
  private closed = false;
  private readonly handlers = new Set<EventHandler>();

  async connect(): Promise<void> {
    await keycloak().updateToken(30);
    const accessToken = keycloak().token;
    if (this.closed || !accessToken) return;

    this.socket = new WebSocket(getWebSocketUrl(), ["access_token", accessToken]);
    this.socket.onopen = () => {
      this.attempt = 0;
      this.socket?.send(JSON.stringify({ op: "subscribe", events: subscriptionEvents }));
    };
    this.socket.onmessage = (message) => {
      const event = JSON.parse(String(message.data)) as PlatformEvent;
      if (event.event_type) this.handlers.forEach((handler) => handler(event));
    };
    this.socket.onclose = () => {
      if (!this.closed) window.setTimeout(() => void this.connect(), Math.min(30_000, 1_000 * 2 ** this.attempt++));
    };
  }

  subscribe(handler: EventHandler): () => boolean {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  close(): void {
    this.closed = true;
    this.socket?.close();
  }
}
