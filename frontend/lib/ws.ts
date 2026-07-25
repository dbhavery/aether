/**
 * Typed WebSocket client for the Aether backend on ws://localhost:8765.
 *
 * Design goals:
 *  - One long-lived connection shared across the app (see `getWsClient()`).
 *  - Auto-reconnect with exponential backoff: 1s → 2s → 4s → 8s → 10s cap.
 *  - Typed send/subscribe keyed off `AnyEventType`.
 *  - Pending sends are queued while CONNECTING and flushed on OPEN, so code
 *    that fires on mount doesn't race the socket handshake.
 *  - Status is observable via `onStatusChange` so the header indicator stays
 *    honest.
 *
 * We deliberately do NOT:
 *  - Abstract the Promise-based request/response pattern here. That lives in
 *    the wizard store because it's wizard-specific (matching submit to result
 *    by step id). Keeping this module pure makes it reusable for chat, which
 *    is pub/sub, not RPC.
 */

import { EventType, type AetherEvent, type AnyEventType, type WsStatus } from "./types";

export type EventHandler<TData = Record<string, unknown>> = (
  event: AetherEvent<TData>,
) => void;

export type StatusHandler = (status: WsStatus, detail?: string) => void;

export interface WsClient {
  connect(): void;
  disconnect(): void;
  send(type: AnyEventType, data?: Record<string, unknown>): void;
  subscribe<TData = Record<string, unknown>>(
    type: AnyEventType,
    handler: EventHandler<TData>,
  ): () => void;
  onStatusChange(handler: StatusHandler): () => void;
  getStatus(): WsStatus;
}

const BACKOFF_STEPS_MS: readonly number[] = [1_000, 2_000, 4_000, 8_000, 10_000];
const HEARTBEAT_INTERVAL_MS = 25_000;

export interface CreateWsClientOptions {
  url: string;
  /** Module name announced in outgoing events (defaults to "frontend"). */
  sourceModule?: string;
  /** Injected `WebSocket` ctor for tests. Defaults to the global one. */
  wsCtor?: typeof WebSocket;
}

export function createWsClient(opts: CreateWsClientOptions): WsClient {
  const { url, sourceModule = "frontend" } = opts;
  const Ctor = opts.wsCtor ?? (typeof WebSocket !== "undefined" ? WebSocket : undefined);
  if (!Ctor) {
    throw new Error("createWsClient: no WebSocket implementation available");
  }

  let socket: WebSocket | null = null;
  let status: WsStatus = "disconnected";
  let statusDetail: string | undefined;
  let reconnectAttempt = 0;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  let intentionallyClosed = false;
  let lastPongAt = 0;
  const outbox: string[] = [];

  const subscribers = new Map<AnyEventType, Set<EventHandler>>();
  const wildcardSubscribers = new Set<EventHandler>();
  const statusHandlers = new Set<StatusHandler>();

  function setStatus(next: WsStatus, detail?: string): void {
    if (status === next && statusDetail === detail) return;
    status = next;
    statusDetail = detail;
    for (const handler of statusHandlers) {
      try {
        handler(status, detail);
      } catch (err) {
        console.error("[ws] status handler threw", err);
      }
    }
  }

  function clearReconnect(): void {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  function clearHeartbeat(): void {
    if (heartbeatTimer !== null) {
      clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
  }

  function startHeartbeat(): void {
    clearHeartbeat();
    heartbeatTimer = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) {
        rawSend({
          type: EventType.PING,
          data: {},
          timestamp: Date.now() / 1000,
          source_module: sourceModule,
        });
      }
    }, HEARTBEAT_INTERVAL_MS);
  }

  function rawSend(event: AetherEvent): void {
    const payload = JSON.stringify(event);
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(payload);
    } else {
      outbox.push(payload);
    }
  }

  function flushOutbox(): void {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    while (outbox.length > 0) {
      const payload = outbox.shift();
      if (payload !== undefined) socket.send(payload);
    }
  }

  function scheduleReconnect(): void {
    if (intentionallyClosed) return;
    clearReconnect();
    const idx = Math.min(reconnectAttempt, BACKOFF_STEPS_MS.length - 1);
    const delay = BACKOFF_STEPS_MS[idx] ?? 10_000;
    reconnectAttempt += 1;
    setStatus("connecting", `retry in ${Math.round(delay / 1000)}s (#${reconnectAttempt})`);
    reconnectTimer = setTimeout(openSocket, delay);
  }

  function dispatch(event: AetherEvent): void {
    const specific = subscribers.get(event.type);
    if (specific) {
      for (const handler of specific) {
        try {
          handler(event);
        } catch (err) {
          console.error(`[ws] handler for ${event.type} threw`, err);
        }
      }
    }
    for (const handler of wildcardSubscribers) {
      try {
        handler(event);
      } catch (err) {
        console.error(`[ws] wildcard handler threw`, err);
      }
    }
  }

  function openSocket(): void {
    if (intentionallyClosed) return;
    clearReconnect();

    setStatus("connecting");
    let next: WebSocket;
    try {
      next = new Ctor!(url);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatus("error", msg);
      scheduleReconnect();
      return;
    }
    socket = next;

    next.onopen = () => {
      reconnectAttempt = 0;
      setStatus("connected");
      flushOutbox();
      startHeartbeat();
    };

    next.onmessage = (msg: MessageEvent) => {
      if (typeof msg.data !== "string") {
        console.warn("[ws] non-string frame ignored");
        return;
      }
      let parsed: unknown;
      try {
        parsed = JSON.parse(msg.data);
      } catch (err) {
        console.error("[ws] malformed JSON frame", err, msg.data);
        return;
      }
      // Heartbeat acks: backend replies to {"type":"ping"} with the bare
      // {"type":"pong"} (no data, no timestamp) — handle inline and skip the
      // dispatcher so the strict event shape doesn't reject it as garbage.
      if (
        parsed &&
        typeof parsed === "object" &&
        (parsed as { type?: unknown }).type === "pong"
      ) {
        lastPongAt = Date.now();
        return;
      }
      const event = coerceAetherEvent(parsed);
      if (!event) {
        console.warn("[ws] frame did not match AetherEvent shape", parsed);
        return;
      }
      dispatch(event);
    };

    next.onerror = (ev: Event) => {
      // Chrome fires error with no useful detail; we keep the detail vague.
      setStatus("error", "socket error");
      console.warn("[ws] socket error", ev);
    };

    next.onclose = (ev: CloseEvent) => {
      clearHeartbeat();
      socket = null;
      if (intentionallyClosed) {
        setStatus("disconnected");
        return;
      }
      const reason = ev.reason || `code ${ev.code}`;
      setStatus("disconnected", reason);
      scheduleReconnect();
    };
  }

  function connect(): void {
    intentionallyClosed = false;
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      return;
    }
    openSocket();
  }

  function disconnect(): void {
    intentionallyClosed = true;
    clearReconnect();
    clearHeartbeat();
    if (socket) {
      try {
        socket.close(1000, "client disconnect");
      } catch {
        // socket already closed — ignore.
      }
      socket = null;
    }
    setStatus("disconnected");
  }

  function send(type: AnyEventType, data: Record<string, unknown> = {}): void {
    const event: AetherEvent = {
      type,
      data,
      timestamp: Date.now() / 1000,
      source_module: sourceModule,
    };
    rawSend(event);
  }

  function subscribe<TData = Record<string, unknown>>(
    type: AnyEventType,
    handler: EventHandler<TData>,
  ): () => void {
    let bucket = subscribers.get(type);
    if (!bucket) {
      bucket = new Set();
      subscribers.set(type, bucket);
    }
    // We erase TData at the subscriber boundary; type-safety is maintained by
    // the caller's explicit type argument, not at runtime.
    const generic = handler as EventHandler;
    bucket.add(generic);
    return () => {
      bucket?.delete(generic);
      if (bucket && bucket.size === 0) {
        subscribers.delete(type);
      }
    };
  }

  function onStatusChange(handler: StatusHandler): () => void {
    statusHandlers.add(handler);
    // Fire once so subscribers see the current state without racing.
    try {
      handler(status, statusDetail);
    } catch (err) {
      console.error("[ws] status handler threw on subscribe", err);
    }
    return () => {
      statusHandlers.delete(handler);
    };
  }

  function getStatus(): WsStatus {
    return status;
  }

  return { connect, disconnect, send, subscribe, onStatusChange, getStatus };
}

/**
 * Coerce a parsed inbound frame into an AetherEvent, defaulting `data` to
 * `{}` when missing or non-object. The strict shape (data must be an object)
 * was rejecting valid backend frames that omit `data` for trivial replies
 * (e.g., the bare `{"type":"pong"}` heartbeat ack), spamming console.warn
 * every 25s. Returning a default-shaped event keeps subscribers honest
 * without losing the type.
 */
function coerceAetherEvent(value: unknown): AetherEvent | null {
  if (value === null || typeof value !== "object") return null;
  const candidate = value as Record<string, unknown>;
  if (typeof candidate.type !== "string" || !candidate.type) return null;
  const data =
    candidate.data && typeof candidate.data === "object"
      ? (candidate.data as Record<string, unknown>)
      : {};
  // request_id isn't on AetherEvent's TS type but the runtime carries it as
  // a passthrough field on `data` when present (server.py copies it there
  // during broadcast). Subscribers that need it read `event.data.request_id`.
  return {
    type: candidate.type as AnyEventType,
    data,
    timestamp:
      typeof candidate.timestamp === "number"
        ? candidate.timestamp
        : Date.now() / 1000,
    source_module:
      typeof candidate.source_module === "string" ? candidate.source_module : "backend",
  };
}

/* -----------------------------------------------------------------------
 * Singleton — the whole app shares one connection.
 * --------------------------------------------------------------------- */

let singleton: WsClient | null = null;
const DEFAULT_WS_URL = "ws://localhost:8765";

export function getWsClient(): WsClient {
  if (singleton) return singleton;
  singleton = createWsClient({ url: DEFAULT_WS_URL, sourceModule: "frontend" });
  return singleton;
}
