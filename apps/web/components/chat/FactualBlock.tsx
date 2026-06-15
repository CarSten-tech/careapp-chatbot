// factual_statement-Block: geprüfte Fachaussage mit Quellenhinweis (§3.5).
// KEIN innerHTML — Text wird als textContent gerendert (§3.7).

import type { OutputBlock } from "@/types/api";
import CitationButton from "./CitationButton";

interface Props {
  block: OutputBlock;
}

export default function FactualBlock({ block }: Props) {
  const hasSource = block.claim_version_ids.length > 0;

  return (
    <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 space-y-2">
      <p className="text-sm text-gray-800 leading-relaxed">{block.text}</p>

      {block.structured_values.map((sv, i) => (
        <span
          key={i}
          className="inline-block text-xs bg-blue-100 text-blue-800 rounded px-2 py-0.5 mr-1"
        >
          {sv.kind === "amount_eur" ? `${sv.value} ${sv.unit ?? "EUR"}` : `${sv.kind}: ${sv.value}`}
        </span>
      ))}

      {hasSource && (
        <div className="flex items-center gap-1 mt-1 flex-wrap">
          <span className="text-xs text-blue-600 font-medium">Geprüfte Quelle</span>
          {block.claim_version_ids.map((cvId) => (
            <CitationButton key={cvId} cvId={cvId} />
          ))}
        </div>
      )}
    </div>
  );
}
