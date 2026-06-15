import type { OutputBlock } from "@/types/api";

interface Props {
  block: OutputBlock;
}

export default function FallbackBlock({ block }: Props) {
  return (
    <div
      className="rounded-lg bg-amber-50 border border-amber-200 p-3"
      role="status"
      aria-live="polite"
    >
      <p className="text-sm text-amber-900">{block.text}</p>
      <p className="text-xs text-amber-700 mt-1">
        Bei weiteren Fragen wenden Sie sich bitte an eine Beratungsstelle (Kreis Neuss / Düsseldorf).
      </p>
    </div>
  );
}
