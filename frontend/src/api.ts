import type {
  ActivityPage,
  DashboardBootstrap,
  RangeKey,
  SnapshotPoint,
} from "./types";

const LOCAL_DEV_API_BASE = "http://localhost:5173";
const PRODUCTION_API_BASE = "https://bridgewood.onrender.com";
const PRODUCTION_FRONTEND_HOSTS = new Set(["bridgewood.vercel.app"]);

function normalizeApiBase(rawValue: string) {
  const parsed = new URL(rawValue);
  const normalizedPath = parsed.pathname.replace(/\/+$/, "");

  // Accept either https://host or https://host/v1 in env configuration.
  if (normalizedPath === "/v1") {
    parsed.pathname = "/";
  } else if (normalizedPath.length > 0) {
    parsed.pathname = normalizedPath;
  }

  return parsed.toString().replace(/\/+$/, "");
}

function resolveApiBase() {
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (configured) {
    return normalizeApiBase(configured);
  }

  if (typeof window === "undefined") {
    return LOCAL_DEV_API_BASE;
  }

  if (PRODUCTION_FRONTEND_HOSTS.has(window.location.hostname)) {
    return PRODUCTION_API_BASE;
  }

  return window.location.origin;
}

const API_BASE = resolveApiBase();

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
  const url = buildUrl(path, params);
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} (${url.toString()})`);
  }
  return (await response.json()) as T;
}

export async function getDashboard(range: RangeKey) {
  return requestJson<DashboardBootstrap>("/dashboard", { range });
}

export async function getActivity(limit = 100, cursor?: string) {
  const params: Record<string, string> = { limit: String(limit) };
  if (cursor) {
    params.cursor = cursor;
  }
  return requestJson<ActivityPage>("/activity", params);
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
