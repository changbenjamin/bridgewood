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

import { formatAxisPct, formatDateTime, formatSignedPct } from "../lib/format";
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
    row[point.agent_id] = point.return_pct;
    grouped.set(key, row);
  }

  return Array.from(grouped.values());
}

function getReturnDomain(
  rows: Record<string, number | string>[],
  visibleAgents: LeaderboardEntry[],
): [number, number] {
  let maxAbsReturn = 0;

  rows.forEach((row) => {
    visibleAgents.forEach((agent) => {
      const value = row[agent.id];
      if (typeof value === "number") {
        maxAbsReturn = Math.max(maxAbsReturn, Math.abs(value));
      }
    });
  });

  const padded = Math.max(1, maxAbsReturn * 1.15);
  return [-padded, padded];
}

export function PerformanceChart({ snapshots, agents, hiddenIds }: Props) {
  const rows = buildRows(snapshots);
  const visibleAgents = agents.filter((agent) => !hiddenIds.includes(agent.id));
  const hasCompetitors = agents.some((agent) => !agent.is_benchmark);
  const showSinglePoint = rows.length < 2;
  const [minReturn, maxReturn] = getReturnDomain(rows, visibleAgents);

  return (
    <div>
      <div className="h-[420px] min-w-0 md:h-[500px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={rows}
            margin={{ top: 16, right: 20, bottom: 4, left: 0 }}
          >
            <CartesianGrid
              stroke="#ded7cc"
              strokeDasharray="2 6"
              vertical={false}
            />
            <ReferenceLine
              y={0}
              stroke="#5b6474"
              strokeDasharray="4 6"
              label={{
                value: "0% baseline",
                position: "insideTopRight",
                fill: "#78716c",
                fontSize: 12,
              }}
            />
            <XAxis
              dataKey="timestamp"
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#8d8678", fontSize: 12 }}
              tickFormatter={(value) => formatDateTime(String(value))}
              minTickGap={26}
              tickMargin={14}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#8d8678", fontSize: 12 }}
              tickFormatter={(value) => formatAxisPct(Number(value))}
              domain={[minReturn, maxReturn]}
              width={76}
              tickMargin={14}
            />
            <Tooltip
              contentStyle={{
                background: "#fffdf9",
                borderRadius: 6,
                border: "1px solid #d8d0c2",
                boxShadow: "0 10px 24px rgba(28, 25, 23, 0.08)",
              }}
              formatter={(value, name) => [
                formatSignedPct(Number(value ?? 0)),
                String(name),
              ]}
              labelFormatter={(label) => formatDateTime(String(label))}
            />
            {visibleAgents.map((agent) => (
              <Line
                key={agent.id}
                type="stepAfter"
                dataKey={agent.id}
                name={agent.name}
                stroke={colorForAgent(agent.id, agent.is_benchmark)}
                strokeWidth={agent.is_benchmark ? 2.2 : 2.6}
                dot={showSinglePoint ? { r: 4, strokeWidth: 0 } : false}
                activeDot={{ r: 4, strokeWidth: 0 }}
                connectNulls
                strokeLinecap="round"
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {showSinglePoint && (
        <div className="mt-3 text-sm text-stone-500">
          Additional marks will appear as new snapshots are recorded during the
          session.
        </div>
      )}

      {!hasCompetitors && (
        <div className="mt-3 border border-sky-200/70 bg-sky-50/60 px-4 py-3 text-sm text-sky-900">
          No agents have been registered yet.
        </div>
      )}
    </div>
  );
}
