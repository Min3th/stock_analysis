export type RunStatus = "queued" | "running" | "ok" | "empty" | "failed";

export interface Run {
  id: string;
  sector: string;
  period: string;
  ticker: string | null;
  offline: boolean;
  status: RunStatus;
  gitCommit: string | null;
  configHash: string | null;
  counts: Record<string, number> | null;
  error: string | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface Group {
  name: string;
  slug: string;
  cached: boolean;
}

export interface Company {
  ticker: string;
  name: string;
  industryGroup: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { message?: string; error?: string };
      message = body.message ?? body.error ?? message;
    } catch {
      /* keep the status text */
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

export const isActive = (status: RunStatus): boolean => status === "queued" || status === "running";

/** The calendar quarter as an output label, for example 2026Q4. */
export function currentPeriodLabel(now: Date = new Date()): string {
  return `${now.getFullYear()}Q${Math.floor(now.getMonth() / 3) + 1}`;
}
