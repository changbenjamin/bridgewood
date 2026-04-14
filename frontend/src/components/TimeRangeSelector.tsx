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
          className={`min-w-[48px] border-r border-stone-300 px-2.5 py-1.5 text-[12px] leading-none font-medium tracking-[0.06em] transition last:border-r-0 ${
            value === range
              ? "bg-stone-900 text-white"
              : "bg-transparent text-stone-600 hover:bg-[#f1ece2]"
          }`}
          style={{ fontSize: "12px" }}
        >
          {range}
        </button>
      ))}
    </div>
  );
}
