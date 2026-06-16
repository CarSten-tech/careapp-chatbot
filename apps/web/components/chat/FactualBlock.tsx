import type { OutputBlock } from "@/types/api";
import CitationButton from "./CitationButton";

interface Props {
  block: OutputBlock;
}

export default function FactualBlock({ block }: Props) {
  return (
    <div className="space-y-1">
      <p className="text-sm leading-relaxed">{block.text}</p>

      {block.structured_values.map((sv, i) => (
        <span key={i} className="inline-block text-xs border border-gray-200 rounded px-2 py-0.5 mr-1 text-gray-600">
          {sv.kind === "amount_eur" ? `${sv.value} ${sv.unit ?? "EUR"}` : `${sv.kind}: ${sv.value}`}
        </span>
      ))}

      {block.claim_version_ids.length > 0 && (
        <div className="flex items-center gap-1 flex-wrap">
          <span className="text-xs text-gray-400">Quelle:</span>
          {block.claim_version_ids.map((cvId) => (
            <CitationButton key={cvId} cvId={cvId} />
          ))}
        </div>
      )}
    </div>
  );
}
