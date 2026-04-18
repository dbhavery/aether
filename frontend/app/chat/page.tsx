"use client";

import { useEffect } from "react";
import { ChatInput } from "@/components/chat/ChatInput";
import { MessageList } from "@/components/chat/MessageList";
import { useChatStore } from "@/lib/stores/chat";
import { useSessionStore } from "@/lib/stores/session";
import { findPersona } from "@/lib/personas";
import { useWizardStore } from "@/lib/stores/wizard";

export default function ChatPage() {
  const messages = useChatStore((s) => s.messages);
  const sendUserMessage = useChatStore((s) => s.sendUserMessage);
  const isResponding = useChatStore((s) => s.isAssistantResponding);
  const subscribeChat = useChatStore((s) => s.subscribe);

  const activePersonaId = useSessionStore((s) => s.activePersonaId);
  const activeDisplayName = useSessionStore((s) => s.activeDisplayName);
  const wsStatus = useSessionStore((s) => s.wsStatus);
  const wizardDisplayName = useWizardStore((s) => s.displayName);
  const wizardPersonaId = useWizardStore((s) => s.selectedAvatarId);

  useEffect(() => {
    const unsub = subscribeChat();
    return unsub;
  }, [subscribeChat]);

  const personaId = activePersonaId ?? wizardPersonaId;
  const persona = personaId ? findPersona(personaId) : undefined;
  const assistantLabel =
    activeDisplayName ?? wizardDisplayName ?? persona?.displayName ?? "Aether";

  return (
    <div className="h-full flex flex-col">
      <StatusStrip
        assistantLabel={assistantLabel}
        personaArchetype={persona?.archetype ?? null}
        wsStatus={wsStatus}
      />
      {messages.length === 0 ? (
        <div className="flex-1 flex items-center justify-center px-6">
          <div className="text-center">
            <p className="text-[18px] text-fg-secondary">Say hi to {assistantLabel}.</p>
            <p className="mt-2 text-[13px] text-fg-muted">
              They're running on your machine. Speak freely.
            </p>
          </div>
        </div>
      ) : (
        <MessageList messages={messages} assistantLabel={assistantLabel} />
      )}
      <ChatInput
        disabled={wsStatus !== "connected" || isResponding}
        placeholder={
          wsStatus === "connected"
            ? `Message ${assistantLabel}`
            : "Waiting for backend…"
        }
        onSubmit={sendUserMessage}
      />
    </div>
  );
}

function StatusStrip({
  assistantLabel,
  personaArchetype,
  wsStatus,
}: {
  assistantLabel: string;
  personaArchetype: string | null;
  wsStatus: string;
}) {
  return (
    <div className="flex items-center gap-4 px-6 py-2 border-b border-border-subtle text-[11px] text-fg-muted">
      <span>
        Talking to <span className="text-fg-secondary">{assistantLabel}</span>
      </span>
      {personaArchetype && (
        <>
          <span aria-hidden>·</span>
          <span className="capitalize">{personaArchetype.replace(/_/g, " ")}</span>
        </>
      )}
      {wsStatus !== "connected" && (
        <span className="ml-auto text-warn">Link {wsStatus}</span>
      )}
    </div>
  );
}
