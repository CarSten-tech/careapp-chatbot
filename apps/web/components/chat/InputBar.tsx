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
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }

  return (
    <div className="border-t border-gray-200 px-4 py-3">
      <div className="flex items-end gap-2">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
          maxLength={2000}
          placeholder="Frage eingeben …"
          aria-label="Nachricht eingeben"
          className="flex-1 resize-none border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-gray-400 disabled:bg-gray-50"
        />
        <button
          type="button"
          onClick={handleSubmit}
          disabled={disabled || !value.trim()}
          aria-label="Senden"
          className="flex-shrink-0 border border-gray-300 rounded px-4 py-2 text-sm hover:bg-gray-50 disabled:text-gray-300 disabled:border-gray-200"
        >
          Senden
        </button>
      </div>
    </div>
  );
}
