import type { RangeKey } from "../types";

const RANGES: RangeKey[] = ["1D", "1W", "1M", "ALL"];

interface Props {
  value: RangeKey;
  onChange: (next: RangeKey) => void;
}

export function TimeRangeSelector({ value, onChange }: Props) {
  return (
    <div className="inline-flex overflow-hidden border border-stone-300 bg-[#f8f5ee]">
      {RANGES.map((range) => (
        <button
          key={range}
          type="button"
          onClick={() => onChange(range)}
          className={`min-w-[58px] border-r border-stone-300 px-3.5 py-2.5 text-xs font-semibold tracking-[0.16em] transition last:border-r-0 ${
            value === range
              ? "bg-stone-900 text-white"
              : "bg-transparent text-stone-600 hover:bg-[#f1ece2]"
          }`}
        >
          {range}
        </button>
      ))}
    </div>
  );
}
