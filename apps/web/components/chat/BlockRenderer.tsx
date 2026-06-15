// Wählt die richtige Komponente je Block-Typ (Allowlist-Analogon auf Client-Seite).
// Unbekannte Block-Typen werden nicht gerendert — kein Passthrough unbekannter Inhalte.

import type { OutputBlock } from "@/types/api";
import FactualBlock from "./FactualBlock";
import FallbackBlock from "./FallbackBlock";
import ClarifyBlock from "./ClarifyBlock";

interface Props {
  block: OutputBlock;
  onAnswer?: (answer: string) => void;
}

export default function BlockRenderer({ block, onAnswer }: Props) {
  switch (block.type) {
    case "factual_statement":
      return <FactualBlock block={block} />;

    case "fallback":
      return <FallbackBlock block={block} />;

    case "clarifying_question":
      return <ClarifyBlock block={block} onAnswer={onAnswer} />;

    case "empathy":
      return <p className="text-sm text-gray-500 leading-relaxed">{block.text}</p>;

    default:
      // Unbekannter Typ: sicher ignorieren (client-seitige Allowlist-Analogie)
      return null;
  }
}
