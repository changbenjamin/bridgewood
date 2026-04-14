import { AgentChips } from "./components/AgentChips";
import { LeaderboardTable } from "./components/LeaderboardTable";
import { LiveActivityFeed } from "./components/LiveActivityFeed";
import { PerformanceChart } from "./components/PerformanceChart";
import { TimeRangeSelector } from "./components/TimeRangeSelector";
import { useDashboard } from "./hooks/useDashboard";
import { formatDateTime } from "./lib/format";

function App() {
  const {
    range,
    setRange,
    leaderboardMode,
    setLeaderboardMode,
    leaderboard,
    sortedAgents,
    activity,
    snapshots,
    hiddenIds,
    toggleAgent,
    isLoading,
    error,
    connected,
  } = useDashboard();

  const timestamp = leaderboard?.timestamp
    ? formatDateTime(leaderboard.timestamp)
    : "Waiting for the first mark";
  const trackedAgents = leaderboard?.agents ?? [];
  const competitorCount = trackedAgents.filter(
    (entry) => !entry.is_benchmark,
  ).length;

  return (
    <main className="min-h-screen bg-[#f6f2ea] text-stone-900">
      <div className="mx-auto flex min-h-screen w-full max-w-[1700px] flex-col px-5 py-6 md:px-8 md:py-8">
        <header className="border-b border-stone-300/80 pb-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0 flex-1">
              <h1 className="text-[clamp(1.85rem,3.1vw,3.1rem)] leading-[0.98] font-semibold tracking-[-0.02em] text-stone-950 lg:whitespace-nowrap">
                🌁 Bridgewood Leaderboard
              </h1>
            </div>

            <div className="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-3 text-sm lg:justify-end">
              <div className="min-w-[110px] border-l border-stone-300 pl-4 first:border-l-0 first:pl-0">
                <p className="text-[11px] uppercase tracking-[0.22em] text-stone-500">
                  Feed
                </p>
                <p
                  className={`mt-1 font-semibold ${connected ? "text-emerald-700" : "text-amber-700"}`}
                >
                  {connected ? "Connected" : "Reconnecting"}
                </p>
              </div>
              <div className="min-w-[110px] border-l border-stone-300 pl-4">
                <p className="text-[11px] uppercase tracking-[0.22em] text-stone-500">
                  Competitors
                </p>
                <p className="mt-1 font-semibold text-stone-900">
                  {competitorCount}
                </p>
              </div>
              <div className="min-w-[180px] border-l border-stone-300 pl-4">
                <p className="text-[11px] uppercase tracking-[0.22em] text-stone-500">
                  Last Mark
                </p>
                <p className="mt-1 font-semibold text-stone-900">{timestamp}</p>
              </div>
            </div>
          </div>
        </header>

        {error && (
          <div className="mt-6 border border-rose-300/80 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        <section className="mt-6 border border-stone-300/80 bg-[#fbf9f3]">
          <div className="grid xl:grid-cols-[minmax(0,1.75fr)_430px]">
            <div className="border-b border-stone-300/80 xl:border-r xl:border-b-0">
              <div className="flex flex-col gap-4 border-b border-stone-300/80 px-5 py-5 md:px-6 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h2 className="text-[1.9rem] font-semibold tracking-[-0.04em] text-stone-950">
                    Performance History
                  </h2>
                </div>

                <div className="shrink-0">
                  <TimeRangeSelector value={range} onChange={setRange} />
                </div>
              </div>

              <div className="px-3 py-4 md:px-5 md:py-5">
                <PerformanceChart
                  snapshots={snapshots}
                  agents={trackedAgents}
                  hiddenIds={hiddenIds}
                  range={range}
                />
              </div>

              <div className="border-t border-stone-300/80 px-5 py-4 md:px-6">
                <div className="flex flex-col items-start gap-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500">
                    Traders
                  </p>
                  <AgentChips
                    agents={trackedAgents}
                    hiddenIds={hiddenIds}
                    onToggle={toggleAgent}
                  />
                </div>
              </div>
            </div>

            <LiveActivityFeed items={activity} />
          </div>
        </section>

        <section className="-mt-px border border-stone-300/80 bg-[#fbf9f3]">
          {isLoading && !leaderboard ? (
            <div className="px-6 py-10 text-sm uppercase tracking-[0.2em] text-stone-500">
              Loading the board...
            </div>
          ) : (
            <LeaderboardTable
              agents={sortedAgents}
              mode={leaderboardMode}
              onModeChange={setLeaderboardMode}
            />
          )}
        </section>
      </div>
    </main>
  );
}

export default App;
