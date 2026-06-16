"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage } from "@/types/api";
import MessageBubble from "./MessageBubble";

interface Props {
  messages: ChatMessage[];
  loading: boolean;
  onAnswer?: (answer: string) => void;
}

export default function MessageList({ messages, loading, onAnswer }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <div
      className="flex-1 overflow-y-auto px-4 py-4 space-y-4"
      role="log"
      aria-label="Gesprächsverlauf"
      aria-live="polite"
      aria-atomic="false"
    >
      {messages.length === 0 && !loading && (
        <p className="text-sm text-gray-400 mt-8 text-center">Wie kann ich helfen?</p>
      )}

      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} onAnswer={onAnswer} />
      ))}

      {loading && (
        <div className="flex justify-start" aria-label="Antwort wird geladen">
          <p className="text-sm text-gray-400">…</p>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
