"use client";

import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { COLUMN_KIND, formatValue, toNumber, type Row } from "@/lib/format";

const CHART_METRICS = ["P/E", "P/B", "ROE", "ROA", "Dividend Yield", "Debt-to-Equity", "Revenue Growth YoY", "EPS Growth YoY"];
const BINS = 8;

/** Counts of issuers per equal-width bin of the values the pipeline produced. */
export function bin(values: number[], bins = BINS): { range: string; low: number; high: number; count: number }[] {
  if (values.length === 0) return [];
  const low = Math.min(...values);
  const high = Math.max(...values);
  if (low === high) return [{ range: String(low), low, high, count: values.length }];
  const width = (high - low) / bins;
  const counts = Array.from({ length: bins }, (_, index) => ({
    low: low + index * width,
    high: low + (index + 1) * width,
    count: 0,
  }));
  for (const value of values) {
    const index = Math.min(bins - 1, Math.floor((value - low) / width));
    counts[index]!.count += 1;
  }
  return counts.map((item) => ({ ...item, range: `${item.low.toPrecision(3)} to ${item.high.toPrecision(3)}` }));
}

export function DistributionChart({ rows }: { rows: Row[] }) {
  const available = CHART_METRICS.filter((name) => rows.some((row) => toNumber(row[name]) !== null));
  const [metric, setMetric] = useState(available[0] ?? "P/E");
  const values = useMemo(
    () => rows.map((row) => toNumber(row[metric])).filter((value): value is number => value !== null),
    [rows, metric],
  );
  const data = useMemo(() => bin(values), [values]);
  const kind = COLUMN_KIND[metric];
  const axisLabel = (value: number) => (kind === "percent" ? `${(value * 100).toFixed(0)}%` : String(value));

  if (available.length === 0) {
    return <p className="text-sm text-muted">No metric has enough values to chart.</p>;
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="block text-xs text-muted">Metric</span>
          <select
            className="rounded border border-line bg-surface px-2 py-1 text-sm"
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
          >
            {available.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
        <span className="pb-1 text-xs text-muted">
          {values.length} issuers with a value; {rows.length - values.length} without
        </span>
      </div>
      <div className="h-56 w-full rounded border border-line bg-surface p-2" role="img" aria-label={`Distribution of ${metric} across issuers`}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="low" tickFormatter={axisLabel} stroke="var(--muted)" fontSize={11} />
            <YAxis allowDecimals={false} stroke="var(--muted)" fontSize={11} />
            <Tooltip
              formatter={(count: number) => [`${count} issuers`, "Count"]}
              labelFormatter={(_label, payload) =>
                payload?.[0] ? `${metric}: ${formatValue(metric, payload[0].payload.low)} to ${formatValue(metric, payload[0].payload.high)}` : ""
              }
              contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", color: "var(--ink)" }}
            />
            <Bar dataKey="count" fill="var(--accent)" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
