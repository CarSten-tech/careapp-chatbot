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
        <div className="text-center text-gray-400 text-sm mt-8">
          Stellen Sie Ihre erste Frage zur Pflegesituation.
        </div>
      )}

      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} onAnswer={onAnswer} />
      ))}

      {loading && (
        <div className="flex justify-start" aria-label="Antwort wird geladen">
          <div className="flex gap-1 px-4 py-3 bg-gray-100 rounded-2xl rounded-tl-sm">
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
