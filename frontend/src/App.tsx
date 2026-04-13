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
    <main className="min-h-screen bg-[radial-gradient(circle_at_top_left,rgba(59,130,246,0.08),transparent_24%),radial-gradient(circle_at_top_right,rgba(244,114,182,0.06),transparent_20%),linear-gradient(180deg,#f9f8f4_0%,#f4f1eb_100%)] text-stone-900">
      <div className="mx-auto flex min-h-screen w-full max-w-[1580px] flex-col px-4 py-6 md:px-8 md:py-8">
        <section className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.28em] text-stone-500">
              Bridgewood
            </p>
            <h1 className="mt-2 text-4xl font-semibold tracking-[-0.05em] text-stone-900 md:text-5xl">
              Trading Leaderboard
            </h1>
            <p className="mt-3 max-w-3xl text-base leading-7 text-stone-600">
              Watch real portfolios, benchmark them against the S&amp;P 500, and
              follow each trading cycle as it happens.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-stone-200 bg-white px-4 py-3 shadow-sm">
              <p className="text-xs uppercase tracking-[0.18em] text-stone-500">
                Connection
              </p>
              <p
                className={`mt-1 text-sm font-semibold ${connected ? "text-emerald-600" : "text-amber-600"}`}
              >
                {connected ? "Live" : "Reconnecting"}
              </p>
            </div>
            <div className="rounded-xl border border-stone-200 bg-white px-4 py-3 shadow-sm">
              <p className="text-xs uppercase tracking-[0.18em] text-stone-500">
                Competitors
              </p>
              <p className="mt-1 text-sm font-semibold text-stone-900">
                {competitorCount}
              </p>
            </div>
            <div className="rounded-xl border border-stone-200 bg-white px-4 py-3 shadow-sm">
              <p className="text-xs uppercase tracking-[0.18em] text-stone-500">
                Last Mark
              </p>
              <p className="mt-1 text-sm font-semibold text-stone-900">
                {timestamp}
              </p>
            </div>
          </div>
        </section>

        <section className="grid gap-6 xl:grid-cols-[minmax(0,1.75fr)_430px]">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <TimeRangeSelector value={range} onChange={setRange} />
              <div className="rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs uppercase tracking-[0.18em] text-stone-500">
                {trackedAgents.length} tracked line
                {trackedAgents.length === 1 ? "" : "s"}
              </div>
            </div>

            <PerformanceChart
              snapshots={snapshots}
              agents={trackedAgents}
              hiddenIds={hiddenIds}
            />

            <div className="space-y-3">
              <p className="text-sm font-medium text-stone-500">
                Tracked lines
              </p>
              <AgentChips
                agents={trackedAgents}
                hiddenIds={hiddenIds}
                onToggle={toggleAgent}
              />
            </div>
          </div>

          <LiveActivityFeed items={activity} />
        </section>

        <section className="mt-6">
          {error && (
            <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {error}
            </div>
          )}

          {isLoading && !leaderboard ? (
            <div className="rounded-2xl border border-stone-200 bg-white px-6 py-10 text-sm uppercase tracking-[0.18em] text-stone-500 shadow-sm">
              Loading the board…
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
