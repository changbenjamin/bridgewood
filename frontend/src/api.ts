import type { DashboardBootstrap, RangeKey, SnapshotPoint } from "./types";

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ??
  (typeof window !== "undefined"
    ? window.location.origin
    : "http://localhost:5173");

function buildUrl(path: string, params?: Record<string, string>) {
  const url = new URL(`/v1${path}`, API_BASE);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      url.searchParams.set(key, value);
    });
  }
  return url;
}

async function requestJson<T>(path: string, params?: Record<string, string>) {
  const response = await fetch(buildUrl(path, params));
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function getDashboard(range: RangeKey) {
  return requestJson<DashboardBootstrap>("/dashboard", { range });
}

export async function getSnapshots(range: RangeKey) {
  return requestJson<SnapshotPoint[]>("/snapshots", { range });
}

export function getLiveFeedUrl() {
  const source = new URL(API_BASE);
  source.protocol = source.protocol === "https:" ? "wss:" : "ws:";
  source.pathname = "/v1/ws/live";
  source.search = "";
  return source.toString();
}
