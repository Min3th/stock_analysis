"use client";

import { useCallback, useEffect, useState } from "react";
import { api, isActive, type Run } from "@/lib/api";
import { LiveLog } from "./live-log";
import { RunForm } from "./run-form";
import { StatusBadge } from "./status-badge";

const formatTime = (value: string | null) =>
  value ? new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—";

export function RunsDashboard() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [watching, setWatching] = useState<string | null>(null);

  const load = useCallback(() => {
    api<Run[]>("/runs")
      .then((list) => {
        setRuns(list);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  const anyActive = runs?.some((run) => isActive(run.status)) ?? false;
  useEffect(() => {
    load();
    const timer = setInterval(load, anyActive ? 2000 : 15000);
    return () => clearInterval(timer);
  }, [load, anyActive]);

  return (
    <div className="space-y-6">
      <RunForm
        onStarted={(runId) => {
          setWatching(runId);
          load();
        }}
      />

      {watching && <LiveLog runId={watching} onStatus={load} />}

      <section className="space-y-2">
        <h2 className="text-lg font-medium">Past runs</h2>
        {error && (
          <p role="alert" className="text-sm text-red-700 dark:text-red-300">
            The run list could not be loaded ({error}). Is the local API running?
          </p>
        )}
        {runs && runs.length === 0 && (
          <p className="text-sm text-muted">No runs yet. Start one above.</p>
        )}
        {runs && runs.length > 0 && (
          <div className="overflow-x-auto rounded border border-line bg-surface">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-line text-xs text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Created</th>
                  <th className="px-3 py-2 font-medium">Industry group</th>
                  <th className="px-3 py-2 font-medium">Period</th>
                  <th className="px-3 py-2 font-medium">Scope</th>
                  <th className="px-3 py-2 font-medium">Mode</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 text-right font-medium">Rows</th>
                  <th className="px-3 py-2 text-right font-medium">Review</th>
                  <th className="px-3 py-2 font-medium">Commit</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id} className="border-b border-line last:border-0" data-testid="run-row">
                    <td className="px-3 py-2 whitespace-nowrap">{formatTime(run.createdAt)}</td>
                    <td className="px-3 py-2">{run.sector}</td>
                    <td className="px-3 py-2">{run.period}</td>
                    <td className="px-3 py-2">{run.ticker ?? "Whole group"}</td>
                    <td className="px-3 py-2">{run.offline ? "Offline" : "Live"}</td>
                    <td className="px-3 py-2">
                      <StatusBadge status={run.status} />
                      {run.error && (
                        <span className="mt-1 block max-w-xs whitespace-pre-wrap text-xs text-red-700 dark:text-red-300">
                          {run.error}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{run.counts?.screening ?? "—"}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{run.counts?.review ?? "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs">{run.gitCommit?.slice(0, 7) ?? "—"}</td>
                    <td className="px-3 py-2 text-right">
                      <button
                        type="button"
                        onClick={() => setWatching(run.id)}
                        className="text-xs text-accent hover:underline"
                      >
                        Output
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
