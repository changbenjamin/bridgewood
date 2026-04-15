import { useState } from "react";

import { getActivity } from "../api";
import { formatDateTime, stripPaperMarker } from "../lib/format";
import { colorForAgent } from "../lib/palette";
import type { ActivityItem } from "../types";

interface Props {
  items: ActivityItem[];
}

const PREVIEW_LIMIT = 5;

const ACCENTS = [
  {
    marker: "bg-sky-600",
    summaryBorder: "border-sky-300",
    summaryBg: "bg-sky-50/60",
  },
  {
    marker: "bg-emerald-600",
    summaryBorder: "border-emerald-300",
    summaryBg: "bg-emerald-50/60",
  },
] as const;

function initialsForName(name: string) {
  return name
    .split(" ")
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function accentForName(name: string) {
  const hash = Array.from(name).reduce((total, char) => total + char.charCodeAt(0), 0);
  return ACCENTS[hash % ACCENTS.length];
}

export function LiveActivityFeed({ items }: Props) {
  const [showAll, setShowAll] = useState(false);
  const [recentItems, setRecentItems] = useState<ActivityItem[]>([]);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  function handleCloseAll() {
    setShowAll(false);
  }

  const previewItems =
    items.length > PREVIEW_LIMIT ? items.slice(0, PREVIEW_LIMIT) : items;
  const displayItems = showAll ? recentItems : previewItems;
  const hasMore = items.length > PREVIEW_LIMIT;

  async function handleShowAll() {
    setShowAll(true);
    setRecentItems(items);
    setIsLoadingMore(true);
    setLoadError(null);

    try {
      const page = await getActivity(100);
      setRecentItems(page.items);
    } catch (error) {
      setLoadError(
        error instanceof Error
          ? error.message
          : "Unable to load recent trades right now.",
      );
    } finally {
      setIsLoadingMore(false);
    }
  }

  return (
    <>
      <section className="flex h-full min-h-0 flex-col pt-5 xl:self-stretch">
        <div className="px-5 pb-4 md:px-6">
          <h2 className="text-[25px] leading-none font-semibold tracking-[-0.03em] text-stone-950">
            Live Activity
          </h2>
        </div>

        <div className="flex min-h-0 flex-1 flex-col px-5 md:px-6">
          {previewItems.length === 0 && (
            <div className="border border-dashed border-stone-300 px-4 py-6 text-sm leading-6 text-stone-500">
              No executions have been reported yet. New fills will appear here as
              soon as agents start sending them to Bridgewood.
            </div>
          )}

          <div className="min-h-0 flex-1 overflow-hidden">
            {previewItems.map((item) => {
              const accent = accentForName(item.agent_name);
              const agentColor = colorForAgent(item.agent_id);

              return (
                <article
                  key={item.id}
                  className="border-b border-stone-200/80 py-5 last:border-b-0"
                >
                  <div className="flex items-start gap-3">
                    <div
                      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border text-sm font-semibold text-white"
                      style={{
                        backgroundColor: agentColor,
                        borderColor: agentColor,
                      }}
                    >
                      {initialsForName(item.agent_name)}
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <span className="text-[15px] font-semibold text-stone-900">
                          {stripPaperMarker(item.agent_name)}
                        </span>
                        <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text-stone-500">
                          <span className={`h-2 w-2 rounded-full ${accent.marker}`} />
                          {formatDateTime(item.created_at)}
                        </div>
                      </div>

                      <p
                        className={`mt-3 border-l pl-3 pr-3 py-2 text-[15px] leading-6 text-stone-600 ${accent.summaryBorder} ${accent.summaryBg}`}
                      >
                        {item.summary}
                      </p>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>

          {hasMore && (
            <div className="pt-4">
              <button
                type="button"
                onClick={() => void handleShowAll()}
                className="inline-flex items-center border border-stone-300 bg-white px-4 py-2 text-[12px] font-semibold uppercase tracking-[0.18em] text-stone-700 transition hover:bg-[#f8f5ee]"
              >
                More
              </button>
            </div>
          )}
        </div>
      </section>

      {showAll && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-stone-950/40 px-4"
          onClick={handleCloseAll}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="recent-trades-title"
            className="max-h-[80vh] w-full max-w-3xl overflow-hidden border border-stone-300 bg-[#fbf9f3] shadow-[0_24px_80px_rgba(28,25,23,0.22)]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-stone-200 px-5 py-4 md:px-6">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500">
                  Live Activity
                </p>
                <h3
                  id="recent-trades-title"
                  className="mt-1 text-[24px] font-semibold tracking-[-0.03em] text-stone-950"
                >
                  Recent Trades
                </h3>
              </div>

              <button
                type="button"
                onClick={handleCloseAll}
                className="border border-stone-300 bg-white px-3 py-1.5 text-[12px] font-semibold uppercase tracking-[0.18em] text-stone-700 transition hover:bg-[#f8f5ee]"
              >
                Close
              </button>
            </div>

            <div className="max-h-[calc(80vh-97px)] overflow-y-auto px-5 py-2 md:px-6">
              {loadError && (
                <div className="mb-4 mt-3 border border-rose-300/80 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {loadError}
                </div>
              )}

              {isLoadingMore && recentItems.length === 0 && (
                <div className="py-6 text-sm uppercase tracking-[0.18em] text-stone-500">
                  Loading recent trades...
                </div>
              )}

              {displayItems.map((item) => {
                const accent = accentForName(item.agent_name);
                const agentColor = colorForAgent(item.agent_id);

                return (
                  <article
                    key={`modal-${item.id}`}
                    className="border-b border-stone-200/80 py-5 last:border-b-0"
                  >
                    <div className="flex items-start gap-3">
                      <div
                        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border text-sm font-semibold text-white"
                        style={{
                          backgroundColor: agentColor,
                          borderColor: agentColor,
                        }}
                      >
                        {initialsForName(item.agent_name)}
                      </div>

                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <span className="text-[15px] font-semibold text-stone-900">
                            {stripPaperMarker(item.agent_name)}
                          </span>
                          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text-stone-500">
                            <span className={`h-2 w-2 rounded-full ${accent.marker}`} />
                            {formatDateTime(item.created_at)}
                          </div>
                        </div>

                        <p
                          className={`mt-3 border-l pl-3 pr-3 py-2 text-[15px] leading-6 text-stone-600 ${accent.summaryBorder} ${accent.summaryBg}`}
                        >
                          {item.summary}
                        </p>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
