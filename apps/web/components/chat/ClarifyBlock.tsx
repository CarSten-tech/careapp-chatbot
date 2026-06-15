"use client";

import type { OutputBlock } from "@/types/api";

interface Props {
  block: OutputBlock;
  onAnswer?: (answer: string) => void;
}

export default function ClarifyBlock({ block, onAnswer }: Props) {
  return (
    <div className="rounded-lg bg-gray-50 border border-gray-200 p-3 space-y-2">
      <p className="text-sm text-gray-800">{block.text}</p>

      {onAnswer && (
        <div className="flex gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => onAnswer("ja")}
            className="text-xs px-3 py-1 rounded-full bg-white border border-gray-300 hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            Ja
          </button>
          <button
            type="button"
            onClick={() => onAnswer("nein")}
            className="text-xs px-3 py-1 rounded-full bg-white border border-gray-300 hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
          >
            Nein
          </button>
        </div>
      )}
    </div>
  );
}
