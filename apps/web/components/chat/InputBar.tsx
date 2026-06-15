"use client";

import { useRef, useState } from "react";

interface Props {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export default function InputBar({ onSend, disabled = false }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function handleSubmit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setValue(e.target.value);
    // Auto-Resize
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3">
      <div className="flex items-end gap-2 max-w-3xl mx-auto">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
          maxLength={2000}
          placeholder="Ihre Frage zur Pflegesituation …"
          aria-label="Nachricht eingeben"
          className="flex-1 resize-none rounded-xl border border-gray-300 px-3 py-2 text-sm
                     focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
                     disabled:bg-gray-50 disabled:text-gray-400 leading-relaxed"
        />
        <button
          type="button"
          onClick={handleSubmit}
          disabled={disabled || !value.trim()}
          aria-label="Senden"
          className="flex-shrink-0 rounded-xl bg-blue-600 text-white px-4 py-2 text-sm font-medium
                     hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500
                     disabled:bg-gray-200 disabled:text-gray-400 transition-colors"
        >
          Senden
        </button>
      </div>
      <p className="text-xs text-gray-400 text-center mt-1">
        {value.length}/2000 Zeichen · Enter zum Senden, Shift+Enter für Zeilenumbruch
      </p>
    </div>
  );
}
