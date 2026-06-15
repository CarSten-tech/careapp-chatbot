import type { ChatMessage } from "@/types/api";
import BlockRenderer from "./BlockRenderer";

interface Props {
  message: ChatMessage;
  onAnswer?: (answer: string) => void;
}

export default function MessageBubble({ message, onAnswer }: Props) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] bg-gray-100 px-3 py-2 text-sm rounded">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] space-y-2">
        {message.disposition === "human_handoff" && (
          <div className="text-xs text-gray-500 border border-gray-200 rounded px-2 py-1">
            Weiterleitung an Beratungsstelle
          </div>
        )}

        {/* Blöcke rendern */}
        {(message.blocks ?? []).map((block, i) => (
          <BlockRenderer key={i} block={block} onAnswer={onAnswer} />
        ))}

        {/* Leere Antwort (should not happen — Fallback) */}
        {(!message.blocks || message.blocks.length === 0) && (
          <p className="text-sm text-gray-500 italic">
            Dazu liegen mir keine geprüften Informationen vor.
          </p>
        )}
      </div>
    </div>
  );
}
