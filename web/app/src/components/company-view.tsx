"use client";

import Link from "next/link";
import { useState } from "react";
import { type Run } from "@/lib/api";
import { CONFIDENCE_LABEL, formatExact, formatValue, MISSING, type Row } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { ExportButton } from "./export-button";
import { HistoryChart } from "./history-chart";
import { LineageDrawer, lineageRows } from "./lineage-drawer";
import { SourceViewer, type SourceRef } from "./source-viewer";

const GROUPS: { title: string; metrics: string[] }[] = [
  {
    title: "Earnings and growth",
    metrics: ["Revenue", "Revenue Growth YoY", "3Y Revenue CAGR", "Net Profit", "Net Profit Growth YoY", "EPS", "EPS Growth YoY", "3Y EPS CAGR", "Operating Profit", "EBIT"],
  },
  { title: "Returns", metrics: ["ROE", "ROA"] },
  {
    title: "Valuation and dividends",
    metrics: ["P/E", "P/B", "Earnings Yield", "Book Value Per Share", "DPS", "Dividend Yield", "Payout Ratio"],
  },
  {
    title: "Balance sheet and cash flow",
    metrics: ["Debt-to-Equity", "Debt-to-Equity incl. Leases", "Net Debt", "Lease Liabilities", "Operating Cash Flow", "Free Cash Flow", "OCF / Net Profit"],
  },
];
const HISTORY_METRICS = ["revenue", "net_profit", "eps", "dps", "total_equity", "operating_cash_flow"];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-medium">{title}</h2>
      {children}
    </section>
  );
}

export function CompanyView({ runId, ticker }: { runId: string; ticker: string }) {
  const run = useApi<Run>(`/runs/${runId}`);
  const query = `?ticker=${encodeURIComponent(ticker)}`;
  const ready = run.data?.status === "ok";
  const screening = useApi<Row[]>(ready ? `/runs/${runId}/screening${query}` : null);
  const ratios = useApi<Row[]>(ready ? `/runs/${runId}/ratios${query}` : null);
  const facts = useApi<Row[]>(ready ? `/runs/${runId}/facts${query}` : null);
  const history = useApi<Row[]>(ready ? `/runs/${runId}/history${query}` : null);
  const flags = useApi<Row[]>(ready ? `/runs/${runId}/flags${query}` : null);
  const review = useApi<Row[]>(ready ? `/runs/${runId}/review${query}` : null);
  const sources = useApi<Row[]>(ready ? `/runs/${runId}/sources${query}` : null);

  const [drawer, setDrawer] = useState<string | null>(null);
  const [source, setSource] = useState<SourceRef | null>(null);

  if (run.error) {
    return <p role="alert" className="text-sm text-red-700 dark:text-red-300">This run could not be loaded ({run.error}).</p>;
  }
  if (!run.data || (ready && screening.loading)) return <p className="text-sm text-muted">Loading…</p>;
  const row = screening.data?.[0];
  if (!ready || !row) {
    return (
      <div className="space-y-2">
        <p className="text-sm">
          <Link href={`/runs/${runId}`} className="text-accent hover:underline">
            ← Run
          </Link>
        </p>
        <p role="alert" className="text-sm">
          {ticker} has no screening row in this run{ready ? "" : ` (the run is ${run.data.status})`}.
        </p>
      </div>
    );
  }

  const notApplicable = new Set(String(row["Not Applicable Metrics"] ?? "").split("; ").filter(Boolean));
  const flagList = String(row.Flags ?? "").split("; ").filter(Boolean);
  const ratioRows = ratios.data ?? [];
  const openSource = (reference: SourceRef) => setSource(reference);

  return (
    <div className="space-y-8">
      <header className="space-y-1">
        <p className="text-sm">
          <Link href={`/runs/${runId}`} className="text-accent hover:underline">
            ← {run.data.sector} · {run.data.period}
          </Link>
        </p>
        <h1 className="text-2xl font-semibold">
          {String(row.Company)} <span className="text-base font-normal text-muted">{ticker}</span>
        </h1>
        <p className="flex flex-wrap gap-3 text-sm text-muted">
          <span>{CONFIDENCE_LABEL[String(row["Data Confidence"])] ?? String(row["Data Confidence"])}</span>
          <span>Income basis: {String(row["Income Period Basis"] ?? MISSING)}</span>
          <span>Cash-flow basis: {String(row["Cash Flow Period Basis"] ?? MISSING)}</span>
          <span>Balance sheet: {String(row["Balance Sheet Date"] ?? MISSING)}</span>
          <span>Price {formatValue("Current Price", row["Current Price"])}</span>
        </p>
        <p className="pt-1">
          <ExportButton label="Download company sheet (PDF)" body={{ type: "company", runId, ticker }} />
        </p>
      </header>

      {GROUPS.map((group) => (
        <Section key={group.title} title={group.title}>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {group.metrics
              .filter((metric) => metric in row)
              .map((metric) => {
                const lineage = lineageRows(ratioRows, metric);
                const applicable = !notApplicable.has(metric);
                const value = row[metric];
                const basis = lineage[0]?.["Period Basis"];
                return (
                  <div key={metric} className="rounded border border-line bg-surface p-3" data-testid={`metric-${metric}`}>
                    <p className="text-xs text-muted">{metric}</p>
                    <p className="text-xl tabular-nums" title={formatExact(value)}>
                      {applicable ? formatValue(metric, value) : "Not applicable"}
                    </p>
                    <p className="min-h-4 text-xs text-muted">
                      {applicable ? (basis ? String(basis) : value === null ? "Withheld or not found" : "") : "Does not describe this type of issuer"}
                    </p>
                    <button
                      type="button"
                      onClick={() => setDrawer(metric)}
                      className="mt-1 text-xs text-accent hover:underline"
                      aria-label={`How ${metric} is calculated`}
                    >
                      How is this calculated?
                    </button>
                  </div>
                );
              })}
          </div>
        </Section>
      ))}

      <Section title="Annual history">
        <p className="text-xs text-muted">Reconciled annual values only; hover a bar for its basis and page.</p>
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {HISTORY_METRICS.map((metric) => (
            <HistoryChart key={metric} metric={metric} rows={history.data ?? []} />
          ))}
        </div>
      </Section>

      <Section title="Flags">
        {flagList.length === 0 ? (
          <p className="text-sm text-muted">No flags for this issuer.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {(flags.data ?? []).map((flag, index) => (
              <li key={index}>
                <span className="font-medium">{String(flag.Flag)}</span>{" "}
                <span className="text-muted">{String(flag.Evidence ?? "")}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Review items">
        {(review.data ?? []).length === 0 ? (
          <p className="text-sm text-muted">Nothing withheld or flagged for review.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {(review.data ?? []).map((item, index) => (
              <li key={index} className="rounded border border-line bg-surface p-2">
                <p>
                  <span className="font-medium">{String(item.Metric)}</span>{" "}
                  <span className="text-muted">· {String(item["Validation Rule"])}</span>
                </p>
                <p className="text-muted">{String(item["Reason for Uncertainty"] ?? "")}</p>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Source documents">
        <ul className="space-y-1 text-sm">
          {(sources.data ?? [])
            .filter((item) => ["annual_report", "interim_statement"].includes(String(item.Type)))
            .map((item) => (
              <li key={String(item["Document ID"])}>
                <button
                  type="button"
                  className="text-accent hover:underline"
                  onClick={() =>
                    openSource({
                      ticker,
                      docId: String(item["Document ID"]),
                      page: 1,
                      title: String(item.Document),
                      quote: "",
                      runId,
                    })
                  }
                >
                  {String(item.Document)}
                </button>{" "}
                <span className="text-muted">
                  · {String(item.Type)} · period {String(item["Period End"]).slice(0, 10)} · {String(item["Source Type"] ?? "")}
                </span>
              </li>
            ))}
        </ul>
      </Section>

      {drawer && (
        <LineageDrawer
          ticker={ticker}
          runId={runId}
          column={drawer}
          ratios={ratioRows}
          facts={facts.data ?? []}
          sources={sources.data ?? []}
          onClose={() => setDrawer(null)}
          onViewSource={openSource}
        />
      )}
      {source && <SourceViewer source={source} onClose={() => setSource(null)} />}
    </div>
  );
}
