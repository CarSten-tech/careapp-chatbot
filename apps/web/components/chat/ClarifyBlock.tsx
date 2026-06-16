"use client";

import type { OutputBlock } from "@/types/api";

interface Props {
  block: OutputBlock;
  onAnswer?: (answer: string) => void;
}

export default function ClarifyBlock({ block, onAnswer }: Props) {
  return (
    <div className="space-y-2">
      <p className="text-sm">{block.text}</p>

      {onAnswer && (
        <div className="flex gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => onAnswer("ja")}
            className="text-xs px-3 py-1 border border-gray-300 rounded hover:bg-gray-50"
          >
            Ja
          </button>
          <button
            type="button"
            onClick={() => onAnswer("nein")}
            className="text-xs px-3 py-1 border border-gray-300 rounded hover:bg-gray-50"
          >
            Nein
          </button>
        </div>
      )}
    </div>
  );
}
