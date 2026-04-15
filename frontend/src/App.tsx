import { AgentChips } from "./components/AgentChips";
import { LeaderboardTable } from "./components/LeaderboardTable";
import { LiveActivityFeed } from "./components/LiveActivityFeed";
import { PerformanceChart } from "./components/PerformanceChart";
import { TimeRangeSelector } from "./components/TimeRangeSelector";
import { useDashboard } from "./hooks/useDashboard";
import { formatDateTime, stripPaperMarker } from "./lib/format";

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
  const leader = [...trackedAgents]
    .filter((entry) => !entry.is_benchmark)
    .sort((left, right) => {
      if (right.return_pct !== left.return_pct) {
        return right.return_pct - left.return_pct;
      }
      return right.total_value - left.total_value;
    })[0];
  const leaderName = leader ? stripPaperMarker(leader.name) : "No leader yet";

  return (
    <main className="min-h-screen bg-[#fbf9f3] text-stone-900">
      <div className="mx-auto flex min-h-screen w-full max-w-[1700px] flex-col px-5 py-6 md:px-8 md:py-8">
        <header className="border-b border-stone-300/80 pb-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0 flex-1">
              <h1 className="text-[clamp(25px,3.1vw,50px)] leading-[0.98] font-semibold tracking-[-0.03em] text-stone-950 lg:whitespace-nowrap">
                🌁 Bridgewood Leaderboard
              </h1>
            </div>

            <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-3 text-sm lg:justify-end">
              <div className="min-w-[150px] border-l border-stone-300 pl-4 first:border-l-0 first:pl-0">
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500">
                  Leader
                </p>
                <p
                  className="mt-1 truncate font-semibold text-stone-900"
                  title={leaderName}
                >
                  {leaderName}
                </p>
              </div>
              <div className="min-w-[110px] border-l border-stone-300 pl-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500">
                  Feed
                </p>
                <p
                  className={`mt-1 font-semibold ${connected ? "text-emerald-700" : "text-amber-700"}`}
                >
                  {connected ? "Connected" : "Reconnecting"}
                </p>
              </div>
              <div className="min-w-[180px] border-l border-stone-300 pl-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500">
                  Last Updated
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

        <section className="mt-3">
          <div className="grid items-start xl:grid-cols-[minmax(0,1.75fr)_430px]">
            <div className="border border-stone-200 bg-white shadow-[0_18px_45px_rgba(28,25,23,0.08)]">
              <div className="flex flex-col gap-4 px-5 py-5 md:px-6 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <h2 className="text-[25px] font-semibold tracking-[-0.03em] text-stone-950">
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

              <div className="px-5 py-4 md:px-6">
                <div className="flex flex-col items-start gap-3">
                  <p className="text-[14px] font-semibold uppercase tracking-[0.22em] text-stone-500">
                    Agents
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

        <section className="mt-3">
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
