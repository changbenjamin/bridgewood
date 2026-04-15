import {
  formatCount,
  formatCurrency,
  formatPct,
  formatSignedCurrency,
  stripPaperMarker,
} from "../lib/format";
import { colorForAgent } from "../lib/palette";
import type { LeaderboardEntry, LeaderboardMode } from "../types";

interface Props {
  agents: LeaderboardEntry[];
  mode: LeaderboardMode;
  onModeChange: (next: LeaderboardMode) => void;
}

const rankDisplay = ["🥇", "🥈", "🥉"];

export function LeaderboardTable({ agents, mode, onModeChange }: Props) {
  const hasCompetitors = agents.some((agent) => !agent.is_benchmark);

  return (
    <section className="px-0 py-5">
      <div className="border border-stone-200 bg-white">
        <div className="flex flex-col gap-4 px-5 py-5 md:px-6 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="text-[25px] leading-none font-semibold tracking-[-0.03em] text-stone-950">
              Leaderboard
            </h2>
          </div>

          <div>
            <div className="inline-flex overflow-hidden border border-stone-300 bg-[#f8f5ee]">
              <button
                type="button"
                onClick={() => onModeChange("all-time")}
                className={`border-r border-stone-300 px-3 py-1.5 text-[12px] leading-none font-medium uppercase tracking-[0.06em] transition ${
                  mode === "all-time"
                    ? "bg-stone-900 text-white"
                    : "text-stone-600 hover:bg-[#f1ece2]"
                }`}
                style={{ fontSize: "12px" }}
              >
                All-time
              </button>
              <button
                type="button"
                onClick={() => onModeChange("daily")}
                className={`px-3 py-1.5 text-[12px] leading-none font-medium uppercase tracking-[0.06em] transition ${
                  mode === "daily"
                    ? "bg-stone-900 text-white"
                    : "text-stone-600 hover:bg-[#f1ece2]"
                }`}
                style={{ fontSize: "12px" }}
              >
                Daily
              </button>
            </div>
          </div>
        </div>

        {!hasCompetitors && (
          <p className="px-5 pb-5 text-sm leading-6 text-stone-500 md:px-6">
            No agents have joined the board yet. Competitors can sign up with
            <span className="mx-1 bg-stone-100 px-1.5 py-0.5 font-mono text-xs text-stone-700">
              POST /v1/signup
            </span>
            and create agents with
            <span className="mx-1 bg-stone-100 px-1.5 py-0.5 font-mono text-xs text-stone-700">
              POST /v1/account/agents
            </span>
            .
          </p>
        )}

        <div className="overflow-x-auto border-t border-stone-200">
          <table className="min-w-full border-collapse">
          <thead>
            <tr className="border-b border-stone-300/80 text-left text-[12px] uppercase tracking-[0.22em] text-stone-500">
              <th className="w-16 px-2 py-4 text-center">Rank</th>
              <th className="px-2 py-4">Agent</th>
              <th className="px-2 py-4">Return</th>
              <th className="px-2 py-4">Day</th>
              <th className="px-2 py-4">Account Value</th>
              <th className="px-2 py-4">PnL</th>
              <th className="px-2 py-4">Sharpe</th>
              <th className="px-2 py-4 text-right">Trades</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((agent, index) => {
              const accent = colorForAgent(agent.id, agent.is_benchmark);
              const rank = index + 1;
              const rankLabel =
                rankDisplay[index] ?? String(rank).padStart(2, "0");
              const isMedalRank = rank <= rankDisplay.length;

              return (
                <tr
                  key={agent.id}
                  className="border-b border-stone-200/80 text-sm text-stone-700 last:border-b-0"
                >
                  <td
                    className={`w-16 px-2 py-5 text-center text-stone-500 ${
                      isMedalRank ? "text-xl" : "font-mono text-xs"
                    }`}
                  >
                    {rankLabel}
                  </td>
                  <td className="px-2 py-5">
                    <div className="flex items-center gap-3">
                      <span
                        className="h-9 w-1.5 shrink-0 rounded-full"
                        style={{ backgroundColor: accent }}
                      />
                      <div>
                        <div className="font-semibold text-stone-950">
                          {stripPaperMarker(agent.name)}
                        </div>
                        <div className="mt-1 text-[11px] uppercase tracking-[0.18em] text-stone-400">
                          {agent.is_benchmark
                            ? "Benchmark"
                            : agent.trading_mode === "live"
                              ? "Live"
                              : "Paper"}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td
                    className={`px-2 py-5 font-medium ${agent.return_pct >= 0 ? "text-emerald-700" : "text-rose-700"}`}
                  >
                    {formatPct(agent.return_pct)}
                  </td>
                  <td
                    className={`px-2 py-5 ${agent.daily_change_pct >= 0 ? "text-emerald-700" : "text-rose-700"}`}
                  >
                    {formatPct(agent.daily_change_pct)}
                  </td>
                  <td className="px-2 py-5 font-semibold text-stone-950">
                    {formatCurrency(agent.total_value)}
                  </td>
                  <td
                    className={`px-2 py-5 ${agent.pnl >= 0 ? "text-emerald-700" : "text-rose-700"}`}
                  >
                    {formatSignedCurrency(agent.pnl)}
                  </td>
                  <td className="px-2 py-5">{agent.sharpe.toFixed(2)}</td>
                  <td className="px-2 py-5 text-right">
                    {formatCount(agent.execution_count)}
                  </td>
                </tr>
              );
            })}
          </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
