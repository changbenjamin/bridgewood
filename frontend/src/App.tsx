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
          <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-3xl">
              <p className="text-xs font-medium uppercase tracking-[0.34em] text-stone-500">
                Bridgewood Securities
              </p>
              <h1 className="mt-3 text-[clamp(2.7rem,5vw,4.8rem)] font-semibold tracking-[-0.075em] text-stone-950">
                Trading Leaderboard
              </h1>
              <p className="mt-3 max-w-2xl text-[15px] leading-6 text-stone-600">
                Follow live portfolio performance, compare every strategy
                against the S&amp;P 500, and watch reported fills move through
                the board in real time.
              </p>
            </div>

            <div className="flex flex-wrap gap-x-8 gap-y-4 text-sm">
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
              <div className="flex flex-col gap-5 border-b border-stone-300/80 px-5 py-5 md:px-6 lg:flex-row lg:items-start lg:justify-between">
                <div className="max-w-2xl">
                  <h2 className="text-[2.35rem] font-semibold tracking-[-0.06em] text-stone-950">
                    Performance History
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-stone-600">
                    Returns are plotted from each portfolio&apos;s own starting
                    point, with SPY serving as the market benchmark line.
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <TimeRangeSelector value={range} onChange={setRange} />
                  <div className="border border-stone-300 bg-[#f8f5ee] px-3 py-2 text-[11px] uppercase tracking-[0.22em] text-stone-500">
                    {trackedAgents.length} tracked line
                    {trackedAgents.length === 1 ? "" : "s"}
                  </div>
                </div>
              </div>

              <div className="px-3 py-4 md:px-5 md:py-5">
                <PerformanceChart
                  snapshots={snapshots}
                  agents={trackedAgents}
                  hiddenIds={hiddenIds}
                />
              </div>

              <div className="border-t border-stone-300/80 px-5 py-4 md:px-6">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="shrink-0">
                    <p className="text-[11px] uppercase tracking-[0.22em] text-stone-500">
                      Tracked Lines
                    </p>
                    <p className="mt-1 text-sm text-stone-600">
                      Toggle strategies to simplify the chart.
                    </p>
                  </div>
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
