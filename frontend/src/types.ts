export type RangeKey = "1D" | "1W" | "1M" | "ALL";
export type LeaderboardMode = "all-time" | "daily";

export interface LeaderboardEntry {
  id: string;
  name: string;
  icon_url?: string | null;
  cash: number;
  total_value: number;
  pnl: number;
  return_pct: number;
  sharpe: number;
  max_win: number;
  max_loss: number;
  execution_count: number;
  is_benchmark?: boolean;
  daily_change_pct: number;
}

export interface LeaderboardPayload {
  type: "leaderboard_update";
  agents: LeaderboardEntry[];
  timestamp: string;
}

export interface ActivityItem {
  id: string;
  agent_id: string;
  agent_name: string;
  icon_url?: string | null;
  event_type: string;
  summary: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ActivityPayload {
  type: "activity";
  agent_id: string;
  agent_name: string;
  icon_url?: string | null;
  summary: string;
  timestamp: string;
}

export interface SnapshotPoint {
  agent_id: string;
  name: string;
  total_value: number;
  snapshot_at: string;
  is_benchmark?: boolean;
  icon_url?: string | null;
}

export interface DashboardBootstrap {
  leaderboard: LeaderboardPayload;
  activity: ActivityItem[];
  snapshots: SnapshotPoint[];
  range: RangeKey;
}

export type LiveMessage = LeaderboardPayload | ActivityPayload;
