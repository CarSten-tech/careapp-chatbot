import type { OutputBlock } from "@/types/api";

interface Props {
  block: OutputBlock;
}

export default function FallbackBlock({ block }: Props) {
  return (
    <div role="status">
      <p className="text-sm text-gray-700">{block.text}</p>
      <p className="text-xs text-gray-400 mt-1">
        Bei weiteren Fragen wenden Sie sich bitte an eine Beratungsstelle (Kreis Neuss / Düsseldorf).
      </p>
    </div>
  );
}
