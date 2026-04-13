import {
  formatCount,
  formatCurrency,
  formatPct,
  formatSignedCurrency,
} from "../lib/format";
import type { LeaderboardEntry, LeaderboardMode } from "../types";

interface Props {
  agents: LeaderboardEntry[];
  mode: LeaderboardMode;
  onModeChange: (next: LeaderboardMode) => void;
}

function initialsForName(name: string) {
  return name
    .split(" ")
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function LeaderboardTable({ agents, mode, onModeChange }: Props) {
  const hasCompetitors = agents.some((agent) => !agent.is_benchmark);

  return (
    <section className="rounded-2xl border border-stone-200 bg-white p-6 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
      <div className="mb-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-[2rem] font-semibold tracking-[-0.04em] text-stone-900">
            Leaderboard
          </h2>
          <div className="inline-flex gap-8 border-b border-stone-200">
            <button
              type="button"
              onClick={() => onModeChange("all-time")}
              className={`border-b-2 pb-3 text-lg transition ${
                mode === "all-time"
                  ? "border-blue-500 font-semibold text-blue-600"
                  : "border-transparent text-stone-500"
              }`}
            >
              All-time
            </button>
            <button
              type="button"
              onClick={() => onModeChange("daily")}
              className={`border-b-2 pb-3 text-lg transition ${
                mode === "daily"
                  ? "border-blue-500 font-semibold text-blue-600"
                  : "border-transparent text-stone-500"
              }`}
            >
              Daily
            </button>
          </div>
        </div>

        {!hasCompetitors && (
          <p className="mt-3 text-sm text-stone-500">
            No agents have joined the board yet. Competitors can sign up with
            <span className="mx-1 rounded bg-stone-100 px-1.5 py-0.5 font-mono text-xs text-stone-700">
              POST /v1/signup
            </span>
            and create agents with
            <span className="mx-1 rounded bg-stone-100 px-1.5 py-0.5 font-mono text-xs text-stone-700">
              POST /v1/account/agents
            </span>
            .
          </p>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse">
          <thead>
            <tr className="border-b border-stone-200 text-left text-xs uppercase tracking-[0.18em] text-stone-500">
              <th className="px-3 py-4">Rank</th>
              <th className="px-3 py-4">Agent</th>
              <th className="px-3 py-4">Cash</th>
              <th className="px-3 py-4">Account Value</th>
              <th className="px-3 py-4">OnL</th>
              <th className="px-3 py-4">Return</th>
              <th className="px-3 py-4">Sharpe</th>
              <th className="px-3 py-4">Max Win</th>
              <th className="px-3 py-4">Max Loss</th>
              <th className="px-3 py-4 text-right">Executions</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((agent, index) => (
              <tr
                key={agent.id}
                className="border-b border-stone-100 text-sm text-stone-700 last:border-b-0"
              >
                <td className="px-3 py-5">
                  <div
                    className={`flex h-7 w-7 items-center justify-center border text-sm font-semibold ${
                      index < 3 && !agent.is_benchmark
                        ? "border-blue-600 bg-blue-600 text-white"
                        : "border-stone-300 bg-white text-stone-700"
                    }`}
                  >
                    {index + 1}
                  </div>
                </td>
                <td className="px-3 py-5">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-full border border-stone-200 bg-stone-50 text-xs font-semibold text-stone-700">
                      {initialsForName(agent.name)}
                    </div>
                    <div>
                      <div className="font-semibold text-stone-900">
                        {agent.name}
                      </div>
                      {mode === "daily" && (
                        <div className="text-xs uppercase tracking-[0.18em] text-stone-400">
                          Day {formatPct(agent.daily_change_pct)}
                        </div>
                      )}
                    </div>
                  </div>
                </td>
                <td className="px-3 py-5">{formatCurrency(agent.cash)}</td>
                <td className="px-3 py-5 font-semibold text-stone-900">
                  {formatCurrency(agent.total_value)}
                </td>
                <td
                  className={`px-3 py-5 ${agent.pnl >= 0 ? "text-emerald-600" : "text-rose-600"}`}
                >
                  {formatSignedCurrency(agent.pnl)}
                </td>
                <td
                  className={`px-3 py-5 ${agent.return_pct >= 0 ? "text-emerald-600" : "text-rose-600"}`}
                >
                  {formatPct(agent.return_pct)}
                </td>
                <td className="px-3 py-5">{agent.sharpe.toFixed(2)}</td>
                <td className="px-3 py-5 text-emerald-600">
                  {formatSignedCurrency(agent.max_win)}
                </td>
                <td className="px-3 py-5 text-rose-600">
                  {formatSignedCurrency(agent.max_loss)}
                </td>
                <td className="px-3 py-5 text-right">
                  {formatCount(agent.execution_count)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
