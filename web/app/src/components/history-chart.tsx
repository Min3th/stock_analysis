"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toNumber, type Row } from "@/lib/format";

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 });

const LABEL: Record<string, string> = {
  revenue: "Revenue",
  net_profit: "Net profit",
  eps: "EPS",
  dps: "DPS",
  total_equity: "Total equity",
  operating_cash_flow: "Operating cash flow",
};

/** One small bar chart per metric from the pipeline's reconciled history rows. */
export function HistoryChart({ metric, rows }: { metric: string; rows: Row[] }) {
  const data = rows
    .filter((row) => row.Metric === metric && toNumber(row.Value) !== null)
    .map((row) => ({
      year: String(row["Financial Year End"]).slice(0, 4),
      end: String(row["Financial Year End"]),
      value: toNumber(row.Value) as number,
      basis: String(row["Value Basis"] ?? ""),
      page: row["Source Page"],
    }))
    .sort((a, b) => a.end.localeCompare(b.end));
  const label = LABEL[metric] ?? metric;
  if (data.length === 0) {
    return (
      <div className="rounded border border-line bg-surface p-3">
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-muted">No reconciled annual values.</p>
      </div>
    );
  }
  return (
    <figure className="rounded border border-line bg-surface p-3">
      <figcaption className="mb-1 text-sm font-medium">{label}</figcaption>
      <div className="h-40" role="img" aria-label={`${label} by financial year: ${data.map((d) => `${d.year} ${compact.format(d.value)}`).join(", ")}`}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="year" stroke="var(--muted)" fontSize={11} />
            <YAxis tickFormatter={(v: number) => compact.format(v)} stroke="var(--muted)" fontSize={11} width={48} />
            <Tooltip
              formatter={(value: number) => [compact.format(value), label]}
              labelFormatter={(_l, payload) =>
                payload?.[0] ? `Year to ${payload[0].payload.end} · ${payload[0].payload.basis} · page ${payload[0].payload.page ?? "?"}` : ""
              }
              contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", color: "var(--ink)" }}
            />
            <Bar dataKey="value" fill="var(--accent)" isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
