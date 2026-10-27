"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { type Run } from "@/lib/api";
import { formatValue, MISSING, type Row } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { DistributionChart } from "./distribution-chart";
import { ScreeningTable } from "./screening-table";
import { StatusBadge } from "./status-badge";

const MEDIAN_PREFIX = "Sector median ";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-medium">{title}</h2>
      {children}
    </section>
  );
}

function Failure({ message }: { message: string }) {
  return (
    <p role="alert" className="text-sm text-red-700 dark:text-red-300">
      {message}
    </p>
  );
}

export function SectorView({ runId }: { runId: string }) {
  const run = useApi<Run>(`/runs/${runId}`);
  const ready = run.data && (run.data.status === "ok" || run.data.status === "empty");
  const screening = useApi<Row[]>(ready ? `/runs/${runId}/screening` : null);
  const summary = useApi<Row[]>(ready ? `/runs/${runId}/summary` : null);
  const flags = useApi<Row[]>(ready ? `/runs/${runId}/flags` : null);
  const review = useApi<Row[]>(ready ? `/runs/${runId}/review` : null);
  const [flagQuery, setFlagQuery] = useState("");

  const medians = useMemo(
    () => (summary.data ?? []).filter((row) => String(row.Metric).startsWith(MEDIAN_PREFIX) && row.Value !== null),
    [summary.data],
  );
  const counts = useMemo(
    () => (summary.data ?? []).filter((row) => String(row.Metric).startsWith("Companies")),
    [summary.data],
  );
  const note = (summary.data ?? []).find((row) => row.Value === null && row.Observations === null)?.Metric;
  const visibleFlags = (flags.data ?? []).filter((row) =>
    `${row.Ticker} ${row.Company} ${row.Flag} ${row.Evidence}`.toLowerCase().includes(flagQuery.toLowerCase()),
  );

  if (run.error) return <Failure message={`This run could not be loaded (${run.error}).`} />;
  if (!run.data) return <p className="text-sm text-muted">Loading run…</p>;
  const info = run.data;

  return (
    <div className="space-y-8">
      <header className="space-y-1">
        <p className="text-sm">
          <Link href="/" className="text-accent hover:underline">
            ← All runs
          </Link>
        </p>
        <h1 className="text-2xl font-semibold">
          {info.sector} · {info.period}
        </h1>
        <p className="flex flex-wrap items-center gap-3 text-sm text-muted">
          <StatusBadge status={info.status} />
          <span>{info.ticker ?? "Whole industry group"}</span>
          <span>{info.offline ? "Offline (cache only)" : "Live"}</span>
          <span>Commit {info.gitCommit?.slice(0, 7) ?? MISSING}</span>
          <span>Config {info.configHash ?? MISSING}</span>
        </p>
      </header>

      {!ready && (
        <Failure
          message={
            info.status === "failed"
              ? `This run failed: ${info.error ?? "no detail recorded"}`
              : "This run has not finished yet; its tables appear when it completes."
          }
        />
      )}

      {info.status === "empty" && (
        <p className="rounded border border-line bg-warn-bg px-3 py-2 text-sm text-warn-ink">
          The run produced no screening rows. The review queue lists why (for example, the CSE
          returned no constituents for this industry group).
        </p>
      )}

      {ready && (
        <>
          <Section title="Summary">
            {summary.error && <Failure message={summary.error} />}
            <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {counts.map((row) => (
                <div key={String(row.Metric)} className="rounded border border-line bg-surface px-3 py-2">
                  <dt className="text-xs text-muted">{String(row.Metric)}</dt>
                  <dd className="text-xl tabular-nums">{String(row.Value)}</dd>
                </div>
              ))}
              <div className="rounded border border-line bg-surface px-3 py-2">
                <dt className="text-xs text-muted">Manual-review items</dt>
                <dd className="text-xl tabular-nums">
                  {review.data?.length ?? MISSING}{" "}
                  <Link href={`/review?run=${runId}`} className="text-sm text-accent hover:underline">
                    Open
                  </Link>
                </dd>
              </div>
            </dl>
            {medians.length > 0 && (
              <div className="overflow-x-auto rounded border border-line bg-surface">
                <table className="w-full text-left text-sm">
                  <caption className="px-3 pt-2 text-left text-xs text-muted">
                    Medians as calculated by the pipeline
                  </caption>
                  <thead className="text-xs text-muted">
                    <tr>
                      <th className="px-3 py-2 font-medium">Metric</th>
                      <th className="px-3 py-2 text-right font-medium">Median</th>
                      <th className="px-3 py-2 text-right font-medium">Issuers</th>
                    </tr>
                  </thead>
                  <tbody>
                    {medians.map((row) => {
                      const metric = String(row.Metric).slice(MEDIAN_PREFIX.length);
                      return (
                        <tr key={metric} className="border-t border-line">
                          <td className="px-3 py-1.5">{metric}</td>
                          <td className="px-3 py-1.5 text-right tabular-nums">{formatValue(metric, row.Value)}</td>
                          <td className="px-3 py-1.5 text-right tabular-nums">{String(row.Observations ?? MISSING)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {note && <p className="text-xs text-muted">{String(note)}</p>}
          </Section>

          <Section title="Screening table">
            {screening.error && <Failure message={screening.error} />}
            {screening.data && screening.data.length > 0 && <ScreeningTable rows={screening.data} runId={runId} />}
            {screening.data && screening.data.length === 0 && <p className="text-sm text-muted">No rows.</p>}
          </Section>

          {screening.data && screening.data.length > 0 && (
            <Section title="Distribution">
              <DistributionChart rows={screening.data} />
            </Section>
          )}

          <Section title="Flags">
            <p className="max-w-prose text-xs text-muted">
              Flags are descriptive evidence that something differs from a threshold or from the sector
              median. They are not scores and do not imply a recommendation.
            </p>
            {flags.error && <Failure message={flags.error} />}
            <input
              className="rounded border border-line bg-surface px-2 py-1 text-sm"
              placeholder="Filter flags"
              aria-label="Filter flags"
              value={flagQuery}
              onChange={(e) => setFlagQuery(e.target.value)}
            />
            {visibleFlags.length === 0 ? (
              <p className="text-sm text-muted">No flags{flagQuery ? " match" : " in this run"}.</p>
            ) : (
              <div className="overflow-x-auto rounded border border-line bg-surface">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-line text-xs text-muted">
                    <tr>
                      <th className="px-3 py-2 font-medium">Ticker</th>
                      <th className="px-3 py-2 font-medium">Flag</th>
                      <th className="px-3 py-2 font-medium">Evidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleFlags.map((row, index) => (
                      <tr key={index} className="border-b border-line last:border-0">
                        <td className="px-3 py-2">
                          <Link className="text-accent hover:underline" href={`/runs/${runId}/${row.Ticker}`}>
                            {String(row.Ticker)}
                          </Link>
                        </td>
                        <td className="px-3 py-2">{String(row.Flag)}</td>
                        <td className="px-3 py-2 text-muted">{String(row.Evidence ?? MISSING)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Section>
        </>
      )}
    </div>
  );
}
