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
        <div className="max-w-[75%] rounded-2xl rounded-tr-sm bg-blue-600 text-white px-4 py-2 text-sm">
          {message.content}
        </div>
      </div>
    );
  }

  // Disposition-spezifisches visuelles Feedback
  const isHandoff = message.disposition === "human_handoff";
  const isNoInfo = message.disposition === "no_verified_information";

  return (
    <div className="flex justify-start">
      <div className={`max-w-[85%] space-y-2 ${isHandoff || isNoInfo ? "w-full" : ""}`}>
        {/* Disposition-Banner für besondere Zustände */}
        {isHandoff && (
          <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
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
