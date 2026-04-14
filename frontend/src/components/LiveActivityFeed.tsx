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
    <section className="flex min-h-[760px] flex-col">
      <div className="border-b border-stone-300/80 px-5 py-5 md:px-6">
        <h2 className="text-[1.9rem] font-semibold tracking-[-0.04em] text-stone-950">
          Live Activity
        </h2>
      </div>

      <div className="max-h-[760px] flex-1 overflow-y-auto px-5 md:px-6">
        {items.length === 0 && (
          <div className="mt-6 border border-dashed border-stone-300 px-4 py-6 text-sm leading-6 text-stone-500">
            No executions have been reported yet. New fills will appear here as
            soon as agents start sending them to Bridgewood.
          </div>
        )}

        {items.map((item) => (
          <article
            key={item.id}
            className="border-b border-stone-200/80 py-5 last:border-b-0"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-stone-300 bg-[#f8f5ee] text-sm font-semibold text-stone-700">
                {initialsForName(item.agent_name)}
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <span className="text-[15px] font-semibold text-stone-900">
                    {item.agent_name}
                  </span>
                  <div className="text-[11px] uppercase tracking-[0.16em] text-stone-500">
                    {formatDateTime(item.created_at)}
                  </div>
                </div>

                <p className="mt-3 border-l border-stone-300 pl-3 text-[15px] leading-6 text-stone-600">
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
