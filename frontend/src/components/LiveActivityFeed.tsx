import { formatDateTime } from "../lib/format";
import type { ActivityItem } from "../types";

interface Props {
  items: ActivityItem[];
}

function initialsForName(name: string) {
  return name
    .split(" ")
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function LiveActivityFeed({ items }: Props) {
  return (
    <section className="rounded-2xl border border-stone-200 bg-white p-5 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
      <div className="mb-5">
        <h2 className="text-[2rem] font-semibold tracking-[-0.04em] text-stone-900">
          Live Activity
        </h2>
      </div>

      <div className="max-h-[560px] space-y-0 overflow-y-auto">
        {items.length === 0 && (
          <div className="rounded-xl border border-dashed border-stone-300 bg-stone-50 px-4 py-6 text-sm leading-6 text-stone-500">
            No executions have been reported yet. Once an agent reports a filled
            Alpaca order, it will appear here in real time.
          </div>
        )}

        {items.map((item) => (
          <article
            key={item.id}
            className="border-t border-stone-200 py-4 first:border-t-0"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-stone-200 bg-stone-50 text-sm font-semibold text-stone-700">
                {initialsForName(item.agent_name)}
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
                  <span className="font-semibold text-stone-900">
                    {item.agent_name}
                  </span>
                  <div className="flex flex-wrap items-center gap-3 text-xs text-stone-500">
                    <span>{formatDateTime(item.created_at)}</span>
                  </div>
                </div>

                <p className="mt-3 text-[15px] leading-6 text-stone-600">
                  {item.summary}
                </p>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
