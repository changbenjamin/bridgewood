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
import type { LeaderboardEntry, RangeKey, SnapshotPoint } from "../types";

interface Props {
  snapshots: SnapshotPoint[];
  agents: LeaderboardEntry[];
  hiddenIds: string[];
  range: RangeKey;
}

interface ChartRow {
  timestamp: string;
  ts: number;
  [agentId: string]: number | string;
}

const hourlyTickFormatter = new Intl.DateTimeFormat("en-US", {
  hour: "numeric",
  hour12: true,
});

const dailyTickFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
});

const monthlyTickFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
});

function buildRows(points: SnapshotPoint[]) {
  const grouped = new Map<string, ChartRow>();

  for (const point of [...points].sort(
    (left, right) =>
      new Date(left.snapshot_at).getTime() -
      new Date(right.snapshot_at).getTime(),
  )) {
    const key = point.snapshot_at;
    const row = grouped.get(key) ?? {
      timestamp: key,
      ts: new Date(key).getTime(),
    };
    row[point.agent_id] = point.return_pct;
    grouped.set(key, row);
  }

  const rows = Array.from(grouped.values()).sort(
    (left, right) => left.ts - right.ts,
  );
  if (rows.length < 2) {
    return rows;
  }

  const expanded: ChartRow[] = [];
  const minuteMs = 60_000;
  const latestValues: Record<string, number> = {};

  rows.forEach((row, index) => {
    Object.entries(row).forEach(([key, value]) => {
      if (key !== "timestamp" && key !== "ts" && typeof value === "number") {
        latestValues[key] = value;
      }
    });

    expanded.push({ ...row });

    const next = rows[index + 1];
    if (!next) {
      return;
    }

    for (let ts = row.ts + minuteMs; ts < next.ts; ts += minuteMs) {
      expanded.push({
        timestamp: new Date(ts).toISOString(),
        ts,
        ...latestValues,
      });
    }
  });

  return expanded;
}

function getReturnDomain(
  rows: ChartRow[],
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

function alignToHour(timestamp: number) {
  const date = new Date(timestamp);
  date.setMinutes(0, 0, 0);
  return date.getTime();
}

function alignToDay(timestamp: number) {
  const date = new Date(timestamp);
  date.setHours(0, 0, 0, 0);
  return date.getTime();
}

function alignToMonth(timestamp: number) {
  const date = new Date(timestamp);
  date.setDate(1);
  date.setHours(0, 0, 0, 0);
  return date.getTime();
}

function buildTicks(range: RangeKey, rows: ChartRow[]) {
  if (rows.length === 0) {
    return undefined;
  }

  const min = rows[0].ts;
  const max = rows[rows.length - 1].ts;

  if (min === max) {
    return [min];
  }

  const ticks: number[] = [];

  if (range === "1D") {
    for (let tick = alignToHour(min); tick <= max; tick += 60 * 60 * 1000) {
      if (tick >= min) {
        ticks.push(tick);
      }
    }
  } else if (range === "1W") {
    for (let tick = alignToDay(min); tick <= max; tick += 24 * 60 * 60 * 1000) {
      if (tick >= min) {
        ticks.push(tick);
      }
    }
  } else if (range === "1M") {
    for (
      let tick = alignToDay(min);
      tick <= max;
      tick += 3 * 24 * 60 * 60 * 1000
    ) {
      if (tick >= min) {
        ticks.push(tick);
      }
    }
  } else {
    for (
      let tick = alignToMonth(min);
      tick <= max;
      tick = new Date(tick).setMonth(new Date(tick).getMonth() + 1)
    ) {
      if (tick >= min) {
        ticks.push(tick);
      }
    }
  }

  const deduped = Array.from(new Set(ticks)).sort(
    (left, right) => left - right,
  );
  if (deduped.length === 0) {
    return [min];
  }
  return deduped;
}

function formatXAxisTick(value: number, range: RangeKey) {
  const date = new Date(value);

  if (range === "1D") {
    return hourlyTickFormatter.format(date).toUpperCase();
  }

  if (range === "ALL") {
    return monthlyTickFormatter.format(date).toUpperCase();
  }

  return dailyTickFormatter.format(date).toUpperCase();
}

export function PerformanceChart({
  snapshots,
  agents,
  hiddenIds,
  range,
}: Props) {
  const rows = buildRows(snapshots);
  const visibleAgents = agents.filter((agent) => !hiddenIds.includes(agent.id));
  const hasCompetitors = agents.some((agent) => !agent.is_benchmark);
  const showSinglePoint = rows.length < 2;
  const [minReturn, maxReturn] = getReturnDomain(rows, visibleAgents);
  const ticks = buildTicks(range, rows);

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
              dataKey="ts"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              ticks={ticks}
              axisLine={false}
              tickLine={false}
              tick={{ fill: "#8d8678", fontSize: 12 }}
              tickFormatter={(value) => formatXAxisTick(Number(value), range)}
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
              labelFormatter={(label) =>
                formatDateTime(new Date(Number(label)).toISOString())
              }
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
