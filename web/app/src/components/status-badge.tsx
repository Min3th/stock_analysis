import type { RunStatus } from "@/lib/api";

const STYLES: Record<RunStatus, string> = {
  queued: "border-line text-muted",
  running: "border-accent text-accent",
  ok: "border-green-700 text-green-800 dark:border-green-400 dark:text-green-300",
  empty: "border-amber-700 text-amber-800 dark:border-amber-400 dark:text-amber-300",
  failed: "border-red-700 text-red-800 dark:border-red-400 dark:text-red-300",
};

const LABELS: Record<RunStatus, string> = {
  queued: "Queued",
  running: "Running",
  ok: "Completed",
  empty: "No rows",
  failed: "Failed",
};

/** Status is always spelled out in text; colour is only a secondary cue. */
export function StatusBadge({ status }: { status: RunStatus }) {
  return (
    <span className={`inline-block rounded border px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}>
      {LABELS[status]}
    </span>
  );
}
