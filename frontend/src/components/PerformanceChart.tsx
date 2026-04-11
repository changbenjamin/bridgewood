import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  formatAxisCurrency,
  formatCurrency,
  formatDateTime,
} from "../lib/format";
import { colorForAgent } from "../lib/palette";
import type { LeaderboardEntry, SnapshotPoint } from "../types";

interface Props {
  snapshots: SnapshotPoint[];
  agents: LeaderboardEntry[];
  hiddenIds: string[];
}

function buildRows(points: SnapshotPoint[]) {
  const grouped = new Map<string, Record<string, number | string>>();

  for (const point of [...points].sort(
    (left, right) =>
      new Date(left.snapshot_at).getTime() -
      new Date(right.snapshot_at).getTime(),
  )) {
    const key = point.snapshot_at;
    const row = grouped.get(key) ?? { timestamp: key };
    row[point.agent_id] = point.total_value;
    grouped.set(key, row);
  }

  return Array.from(grouped.values());
}

export function PerformanceChart({ snapshots, agents, hiddenIds }: Props) {
  const rows = buildRows(snapshots);
  const visibleAgents = agents.filter((agent) => !hiddenIds.includes(agent.id));
  const hasCompetitors = agents.some((agent) => !agent.is_benchmark);
  const showSinglePoint = rows.length < 2;

  return (
    <div className="rounded-2xl border border-stone-200 bg-white p-5 shadow-[0_16px_40px_rgba(15,23,42,0.06)] md:p-6">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1.5">
          <h2 className="text-[2rem] font-semibold tracking-[-0.04em] text-stone-900">
            Performance History
          </h2>
          <p className="max-w-3xl text-sm text-stone-500">
            * Entries with asterisks are paper-trading accounts. The S&amp;P 500
            line uses SPY as the proxy benchmark.
          </p>
        </div>
        <div className="rounded-lg border border-stone-200 bg-stone-50 px-3 py-2 text-xs uppercase tracking-[0.18em] text-stone-500">
          Starting Cash {formatCurrency(10000)}
        </div>
      </div>

      <div className="h-[360px] min-w-0">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={rows}
            margin={{ top: 12, right: 24, bottom: 0, left: 0 }}
          >
            <CartesianGrid stroke="#ede7dd" vertical={false} />
            <ReferenceLine
              y={10000}
              stroke="#a8a29e"
              strokeDasharray="6 6"
              label={{
                value: "$10K starting cash",
                position: "insideBottomRight",
                fill: "#a8a29e",
                fontSize: 12,
              }}
            />
            <XAxis
              dataKey="timestamp"
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#78716c", fontSize: 12 }}
              tickFormatter={(value) => formatDateTime(String(value))}
              minTickGap={24}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#78716c", fontSize: 12 }}
              tickFormatter={(value) => formatAxisCurrency(Number(value))}
              width={84}
            />
            <Tooltip
              contentStyle={{
                background: "#ffffff",
                borderRadius: 16,
                border: "1px solid #e7e5e4",
                boxShadow: "0 16px 36px rgba(15, 23, 42, 0.1)",
              }}
              formatter={(value, name) => [
                formatCurrency(Number(value ?? 0)),
                String(name),
              ]}
              labelFormatter={(label) => formatDateTime(String(label))}
            />
            {visibleAgents.map((agent) => (
              <Line
                key={agent.id}
                type="monotone"
                dataKey={agent.id}
                name={agent.name}
                stroke={colorForAgent(agent.id, agent.is_benchmark)}
                strokeWidth={agent.is_benchmark ? 2.5 : 2.8}
                dot={showSinglePoint ? { r: 4, strokeWidth: 0 } : false}
                activeDot={{ r: 4, strokeWidth: 0 }}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {showSinglePoint && (
        <div className="mt-4 text-sm text-stone-500">
          The chart will fill in as additional snapshots are captured throughout
          the session.
        </div>
      )}

      {!hasCompetitors && (
        <div className="mt-4 rounded-xl border border-sky-100 bg-sky-50 px-4 py-3 text-sm text-sky-900">
          No agents have been registered yet.
        </div>
      )}
    </div>
  );
}
