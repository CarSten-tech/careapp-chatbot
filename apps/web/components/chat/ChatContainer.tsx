"use client";

import { useState, useCallback } from "react";
import type { ChatMessage, Disposition } from "@/types/api";
import { sendMessage, ApiError } from "@/lib/api-client";
import MessageList from "./MessageList";
import InputBar from "./InputBar";

interface Props {
  initialSessionId?: string | null;
}

let msgCounter = 0;
function nextId() {
  return `msg-${++msgCounter}`;
}

export default function ChatContainer({ initialSessionId }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(
    initialSessionId ?? null
  );

  const handleSend = useCallback(
    async (text: string) => {
      if (loading) return;

      // Optimistisch Nutzer-Nachricht anhängen
      const userMsg: ChatMessage = {
        id: nextId(),
        role: "user",
        content: text,
      };
      setMessages((prev) => [...prev, userMsg]);
      setLoading(true);

      try {
        const data = await sendMessage(text, sessionId);
        setSessionId(data.session_id);

        const assistantMsg: ChatMessage = {
          id: nextId(),
          role: "assistant",
          content: "",
          blocks: data.blocks,
          disposition: data.disposition as Disposition,
          turn: data.turn,
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        const errorText =
          err instanceof ApiError
            ? `Fehler ${err.status} — bitte versuchen Sie es erneut.`
            : "Die Verbindung wurde unterbrochen. Bitte versuchen Sie es erneut.";

        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "assistant",
            content: "",
            blocks: [{ type: "fallback", text: errorText, claim_version_ids: [], structured_values: [] }],
            disposition: "no_verified_information",
          },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [loading, sessionId]
  );

  // Rückfragen-Antwort: direkt als neue Nutzer-Nachricht senden
  const handleAnswer = useCallback(
    (answer: string) => {
      handleSend(answer);
    },
    [handleSend]
  );

  return (
    <div className="flex flex-col h-full">
      <MessageList
        messages={messages}
        loading={loading}
        onAnswer={handleAnswer}
      />
      <InputBar onSend={handleSend} disabled={loading} />
    </div>
  );
}
