import type { RangeKey } from "../types";

const RANGES: RangeKey[] = ["1D", "1W", "1M", "ALL"];

interface Props {
  value: RangeKey;
  onChange: (next: RangeKey) => void;
}

export function TimeRangeSelector({ value, onChange }: Props) {
  return (
    <div className="inline-flex overflow-hidden rounded-lg border border-stone-200 bg-white shadow-sm">
      {RANGES.map((range) => (
        <button
          key={range}
          type="button"
          onClick={() => onChange(range)}
          className={`border-r border-stone-200 px-3.5 py-2 text-xs font-semibold tracking-[0.16em] transition last:border-r-0 ${
            value === range
              ? "bg-stone-900 text-white"
              : "bg-white text-stone-600 hover:bg-stone-50"
          }`}
        >
          {range}
        </button>
      ))}
    </div>
  );
}
