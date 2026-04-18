/**
 * Chat message store with streaming token assembly.
 *
 * Handles:
 *  - User-sent messages (appended immediately, optimistic).
 *  - Assistant messages via RESPONSE_TEXT_READY (full reply) OR via
 *    RESPONSE_TEXT_CHUNK tokens finalized on RESPONSE_TEXT_READY /
 *    RESPONSE_END. We always end up with one canonical assistant entry per
 *    turn regardless of whether the backend streams or flushes.
 */

"use client";

import { create } from "zustand";
import { getWsClient } from "../ws";
import { EventType, ExtendedEventType, type MessageRole } from "../types";

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  /** Timestamp in ms since epoch (consistent across UI). */
  timestamp: number;
  streaming: boolean;
}

export interface ChatState {
  messages: ChatMessage[];
  isAssistantResponding: boolean;
  subscribed: boolean;
  subscribe(): () => void;
  sendUserMessage(text: string): void;
  clear(): void;
}

let messageCounter = 0;
function nextMessageId(prefix: string): string {
  messageCounter += 1;
  return `${prefix}-${Date.now().toString(36)}-${messageCounter}`;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isAssistantResponding: false,
  subscribed: false,

  subscribe() {
    if (get().subscribed) return () => {};
    set({ subscribed: true });

    const ws = getWsClient();
    const unsubs: Array<() => void> = [];

    const ensureStreamingAssistant = (): ChatMessage => {
      const existing = get().messages[get().messages.length - 1];
      if (existing && existing.role === "assistant" && existing.streaming) {
        return existing;
      }
      const fresh: ChatMessage = {
        id: nextMessageId("asst"),
        role: "assistant",
        content: "",
        timestamp: Date.now(),
        streaming: true,
      };
      set({ messages: [...get().messages, fresh], isAssistantResponding: true });
      return fresh;
    };

    unsubs.push(
      ws.subscribe(ExtendedEventType.RESPONSE_START, () => {
        ensureStreamingAssistant();
      }),
    );

    unsubs.push(
      ws.subscribe(ExtendedEventType.RESPONSE_TEXT_CHUNK, (event) => {
        const chunk = (event.data as { text?: string; delta?: string }).text
          ?? (event.data as { delta?: string }).delta
          ?? "";
        if (!chunk) return;
        const target = ensureStreamingAssistant();
        set({
          messages: get().messages.map((m) =>
            m.id === target.id ? { ...m, content: m.content + chunk } : m,
          ),
        });
      }),
    );

    unsubs.push(
      ws.subscribe(EventType.RESPONSE_TEXT_READY, (event) => {
        const fullText = (event.data as { text?: string; content?: string }).text
          ?? (event.data as { content?: string }).content
          ?? "";
        const last = get().messages[get().messages.length - 1];
        if (last && last.role === "assistant" && last.streaming) {
          // Finalize the streaming message. If the backend sends the full
          // text here (non-streaming path), overwrite; if it only sent
          // chunks already, leave the accumulated content alone.
          const finalContent = fullText && fullText.length >= last.content.length ? fullText : last.content;
          set({
            messages: get().messages.map((m) =>
              m.id === last.id ? { ...m, content: finalContent, streaming: false } : m,
            ),
            isAssistantResponding: false,
          });
        } else if (fullText) {
          set({
            messages: [
              ...get().messages,
              {
                id: nextMessageId("asst"),
                role: "assistant",
                content: fullText,
                timestamp: Date.now(),
                streaming: false,
              },
            ],
            isAssistantResponding: false,
          });
        } else {
          set({ isAssistantResponding: false });
        }
      }),
    );

    unsubs.push(
      ws.subscribe(ExtendedEventType.RESPONSE_END, () => {
        const last = get().messages[get().messages.length - 1];
        if (last && last.streaming) {
          set({
            messages: get().messages.map((m) =>
              m.id === last.id ? { ...m, streaming: false } : m,
            ),
          });
        }
        set({ isAssistantResponding: false });
      }),
    );

    unsubs.push(
      ws.subscribe(EventType.ERROR, (event) => {
        const msg = (event.data as { message?: string }).message ?? "Backend error.";
        set({
          messages: [
            ...get().messages,
            {
              id: nextMessageId("sys"),
              role: "system",
              content: msg,
              timestamp: Date.now(),
              streaming: false,
            },
          ],
          isAssistantResponding: false,
        });
      }),
    );

    return () => {
      for (const u of unsubs) u();
      set({ subscribed: false });
    };
  },

  sendUserMessage(text) {
    const trimmed = text.trim();
    if (!trimmed) return;
    const msg: ChatMessage = {
      id: nextMessageId("user"),
      role: "user",
      content: trimmed,
      timestamp: Date.now(),
      streaming: false,
    };
    set({
      messages: [...get().messages, msg],
      isAssistantResponding: true,
    });
    getWsClient().send(EventType.USER_MESSAGE, { text: trimmed, content: trimmed });
  },

  clear() {
    set({ messages: [], isAssistantResponding: false });
  },
}));
