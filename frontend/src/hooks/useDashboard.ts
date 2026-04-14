import { startTransition, useEffect, useMemo, useState } from "react";

import { getDashboard, getLiveFeedUrl } from "../api";
import type {
  ActivityItem,
  ActivityPayload,
  LeaderboardMode,
  LeaderboardPayload,
  LiveMessage,
  RangeKey,
  SnapshotPoint,
} from "../types";
import { useWebSocket } from "./useWebSocket";

const RANGE_MS: Record<Exclude<RangeKey, "ALL">, number> = {
  "1D": 24 * 60 * 60 * 1000,
  "1W": 7 * 24 * 60 * 60 * 1000,
  "1M": 30 * 24 * 60 * 60 * 1000,
};

function trimSnapshots(points: SnapshotPoint[], range: RangeKey) {
  if (range === "ALL") {
    return points;
  }
  const cutoff = Date.now() - RANGE_MS[range];
  return points.filter(
    (point) => new Date(point.snapshot_at).getTime() >= cutoff,
  );
}

function appendLiveSnapshots(
  points: SnapshotPoint[],
  leaderboard: LeaderboardPayload,
  range: RangeKey,
) {
  const timestamp = leaderboard.timestamp;
  const additions = leaderboard.agents.map((agent) => ({
    agent_id: agent.id,
    name: agent.name,
    total_value: agent.total_value,
    return_pct: agent.return_pct,
    snapshot_at: timestamp,
    is_benchmark: agent.is_benchmark,
    icon_url: agent.icon_url,
  }));

  const merged = [...points];
  additions.forEach((addition) => {
    const existingIndex = merged.findIndex(
      (point) =>
        point.agent_id === addition.agent_id &&
        point.snapshot_at === addition.snapshot_at,
    );
    if (existingIndex >= 0) {
      merged[existingIndex] = addition;
    } else {
      merged.push(addition);
    }
  });
  return trimSnapshots(merged, range);
}

function leaderboardToSnapshots(
  leaderboard: LeaderboardPayload,
): SnapshotPoint[] {
  return leaderboard.agents.map((agent) => ({
    agent_id: agent.id,
    name: agent.name,
    total_value: agent.total_value,
    return_pct: agent.return_pct,
    snapshot_at: leaderboard.timestamp,
    is_benchmark: agent.is_benchmark,
    icon_url: agent.icon_url,
  }));
}

function toActivityItem(event: ActivityPayload): ActivityItem {
  return {
    id: `${event.agent_id}:${event.timestamp}`,
    agent_id: event.agent_id,
    agent_name: event.agent_name,
    icon_url: event.icon_url,
    event_type: "execution",
    summary: event.summary,
    metadata: {},
    created_at: event.timestamp,
  };
}

export function useDashboard() {
  const [range, setRange] = useState<RangeKey>("1D");
  const [leaderboardMode, setLeaderboardMode] =
    useState<LeaderboardMode>("all-time");
  const [leaderboard, setLeaderboard] = useState<LeaderboardPayload | null>(
    null,
  );
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [snapshots, setSnapshots] = useState<SnapshotPoint[]>([]);
  const [hiddenIds, setHiddenIds] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadInitialData() {
      setIsLoading(true);
      setError(null);
      try {
        const payload = await getDashboard(range);
        if (!active) {
          return;
        }
        setLeaderboard(payload.leaderboard);
        setActivity(payload.activity);
        setSnapshots(
          payload.snapshots.length > 0
            ? payload.snapshots
            : leaderboardToSnapshots(payload.leaderboard),
        );
      } catch (loadError) {
        if (!active) {
          return;
        }
        setError(
          loadError instanceof Error
            ? loadError.message
            : "Unable to load dashboard",
        );
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    void loadInitialData();
    return () => {
      active = false;
    };
  }, [range]);

  const handleMessage = (message: LiveMessage) => {
    if (message.type === "leaderboard_update") {
      startTransition(() => {
        setLeaderboard(message);
        setSnapshots((current) => appendLiveSnapshots(current, message, range));
      });
      return;
    }

    setActivity((current) =>
      [toActivityItem(message), ...current].slice(0, 30),
    );
  };

  const { connected } = useWebSocket<LiveMessage>(
    getLiveFeedUrl(),
    handleMessage,
  );

  const visibleAgents = useMemo(() => leaderboard?.agents ?? [], [leaderboard]);

  const sortedAgents = useMemo(() => {
    const source = [...visibleAgents];
    if (leaderboardMode === "daily") {
      source.sort(
        (left, right) => right.daily_change_pct - left.daily_change_pct,
      );
      return source;
    }
    source.sort((left, right) => right.total_value - left.total_value);
    return source;
  }, [leaderboardMode, visibleAgents]);

  const toggleAgent = (agentId: string) => {
    setHiddenIds((current) =>
      current.includes(agentId)
        ? current.filter((id) => id !== agentId)
        : [...current, agentId],
    );
  };

  return {
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
  };
}
