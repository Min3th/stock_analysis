"use client";

import type { ReactNode } from "react";
import type { Run } from "@/lib/api";
import { DISCLAIMER } from "@/lib/disclaimer";
import { formatExact, formatValue, MISSING, toNumber, type Row } from "@/lib/format";
import { useApi, type Loaded } from "@/lib/use-api";
import { lineageRows, parseFactId } from "./lineage-drawer";

const SUMMARY_PREFIX = "Sector median ";
const HISTORY_METRICS = ["revenue", "net_profit", "eps", "dps", "total_equity", "operating_cash_flow"];

function Shell({ ready, error, children }: { ready: boolean; error: string | null; children: ReactNode }) {
  if (error) {
    return (
      <p role="alert" data-print-error="true" className="text-sm">
        This report could not be built: {error}
      </p>
    );
  }
  return (
    <article data-print-ready={ready ? "true" : "false"} className="print-doc space-y-6 text-[11px] leading-snug">
      {ready ? children : <p>Preparing report…</p>}
    </article>
  );
}

function Cover({ title, subtitle, run, extra }: { title: string; subtitle: string; run: Run; extra?: string }) {
  return (
    <header className="space-y-2 border-b border-line pb-4">
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="text-base">{subtitle}</p>
      <dl className="grid grid-cols-[9rem_1fr] gap-y-0.5">
        <dt className="text-muted">Run</dt>
        <dd className="font-mono">{run.id}</dd>
        <dt className="text-muted">Scope</dt>
        <dd>{run.ticker ?? "Whole industry group"}, {run.offline ? "offline (cache only)" : "live"}</dd>
        <dt className="text-muted">Pipeline commit</dt>
        <dd className="font-mono">{run.gitCommit ?? MISSING}</dd>
        <dt className="text-muted">Config hash</dt>
        <dd className="font-mono">{run.configHash ?? MISSING}</dd>
        <dt className="text-muted">Run finished</dt>
        <dd>{run.finishedAt ?? MISSING}</dd>
        {extra && (
          <>
            <dt className="text-muted">Contents</dt>
            <dd>{extra}</dd>
          </>
        )}
      </dl>
      <p className="rounded border border-line bg-warn-bg px-3 py-2 text-warn-ink">{DISCLAIMER}</p>
    </header>
  );
}

function Table({ caption, head, rows, numeric = [] }: { caption?: string; head: string[]; rows: ReactNode[][]; numeric?: number[] }) {
  return (
    <table className="w-full border-collapse text-left">
      {caption && <caption className="pb-1 text-left text-xs font-medium">{caption}</caption>}
      <thead>
        <tr className="border-b border-line text-muted">
          {head.map((cell, index) => (
            <th key={cell} className={`px-1.5 py-1 font-medium ${numeric.includes(index) ? "text-right" : ""}`}>
              {cell}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((cells, index) => (
          <tr key={index} className="border-b border-line align-top">
            {cells.map((cell, position) => (
              <td key={position} className={`px-1.5 py-1 ${numeric.includes(position) ? "text-right tabular-nums" : ""}`}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const settled = (...loads: Loaded<unknown>[]) => loads.every((load) => !load.loading && load.data !== null);
const firstError = (...loads: Loaded<unknown>[]) => loads.find((load) => load.error)?.error ?? null;

const SECTOR_COLUMNS = ["Current Price", "Market Cap", "Revenue", "Net Profit", "EPS", "ROE", "ROA", "P/E", "P/B", "DPS", "Dividend Yield", "Debt-to-Equity"];

export function SectorPrint({ runId }: { runId: string }) {
  const run = useApi<Run>(`/runs/${runId}`);
  const screening = useApi<Row[]>(`/runs/${runId}/screening`);
  const summary = useApi<Row[]>(`/runs/${runId}/summary`);
  const flags = useApi<Row[]>(`/runs/${runId}/flags`);
  const sources = useApi<Row[]>(`/runs/${runId}/sources`);
  const review = useApi<Row[]>(`/runs/${runId}/review`);
  const loads = [run, screening, summary, flags, sources, review];
  const ready = settled(...loads);
  const counts = (summary.data ?? []).filter((row) => String(row.Metric).startsWith("Companies"));
  const medians = (summary.data ?? []).filter((row) => String(row.Metric).startsWith(SUMMARY_PREFIX) && row.Value !== null);
  const note = (summary.data ?? []).find((row) => row.Value === null && row.Observations === null)?.Metric;
  const documents = (sources.data ?? []).filter((row) => ["annual_report", "interim_statement"].includes(String(row.Type)));

  return (
    <Shell ready={ready} error={firstError(...loads)}>
      {run.data && (
        <>
          <Cover title="Sector screening report" subtitle={`${run.data.sector}, ${run.data.period}`} run={run.data} extra="Summary, screening table, flags, sources appendix" />
          <section>
            <h2 className="mb-1 text-base font-medium">Summary</h2>
            <Table head={["Measure", "Value"]} rows={[...counts.map((row) => [String(row.Metric), String(row.Value)]), ["Manual-review items", String(review.data?.length ?? 0)]]} numeric={[1]} />
            {medians.length > 0 && (
              <div className="mt-3">
                <Table
                  caption="Sector medians as calculated by the pipeline"
                  head={["Metric", "Median", "Issuers"]}
                  numeric={[1, 2]}
                  rows={medians.map((row) => {
                    const metric = String(row.Metric).slice(SUMMARY_PREFIX.length);
                    return [metric, formatValue(metric, row.Value), String(row.Observations ?? MISSING)];
                  })}
                />
              </div>
            )}
            {note && <p className="mt-1 text-muted">{String(note)}</p>}
          </section>
          <section>
            <h2 className="mb-1 text-base font-medium">Screening table</h2>
            <p className="mb-1 text-muted">Ordered by ticker. “—” means no value passed the checks.</p>
            <Table
              head={["Ticker", "Company", ...SECTOR_COLUMNS, "Confidence", "Income basis"]}
              numeric={SECTOR_COLUMNS.map((_, index) => index + 2)}
              rows={(screening.data ?? []).map((row) => [
                String(row.Ticker),
                String(row.Company),
                ...SECTOR_COLUMNS.map((name) => formatValue(name, row[name])),
                String(row["Data Confidence"] ?? MISSING),
                String(row["Income Period Basis"] ?? MISSING),
              ])}
            />
          </section>
          <section>
            <h2 className="mb-1 text-base font-medium">Flags</h2>
            <p className="mb-1 text-muted">Descriptive evidence only; flags are not scores and do not imply a recommendation.</p>
            <Table head={["Ticker", "Flag", "Evidence"]} rows={(flags.data ?? []).map((row) => [String(row.Ticker), String(row.Flag), String(row.Evidence ?? "")])} />
          </section>
          <section>
            <h2 className="mb-1 text-base font-medium">Sources appendix</h2>
            <Table
              head={["Ticker", "Document", "Period end", "Source", "SHA-256 (first 16)"]}
              rows={documents.map((row) => [
                String(row.Ticker),
                String(row.Document),
                String(row["Period End"]).slice(0, 10),
                <span key="u" className="break-all">{String(row["Source URL"] ?? MISSING)}</span>,
                <code key="s">{String(row.SHA256 ?? "").slice(0, 16)}</code>,
              ])}
            />
          </section>
        </>
      )}
    </Shell>
  );
}

const METRIC_GROUPS: [string, string[]][] = [
  ["Earnings and growth", ["Revenue", "Revenue Growth YoY", "3Y Revenue CAGR", "Net Profit", "Net Profit Growth YoY", "EPS", "EPS Growth YoY", "3Y EPS CAGR", "Operating Profit"]],
  ["Returns and valuation", ["ROE", "ROA", "P/E", "P/B", "Earnings Yield", "Book Value Per Share", "DPS", "Dividend Yield", "Payout Ratio"]],
  ["Balance sheet and cash flow", ["Debt-to-Equity", "Debt-to-Equity incl. Leases", "Net Debt", "Lease Liabilities", "Operating Cash Flow", "Free Cash Flow", "OCF / Net Profit"]],
];

export function CompanyPrint({ runId, ticker }: { runId: string; ticker: string }) {
  const q = `?ticker=${encodeURIComponent(ticker)}`;
  const run = useApi<Run>(`/runs/${runId}`);
  const screening = useApi<Row[]>(`/runs/${runId}/screening${q}`);
  const ratios = useApi<Row[]>(`/runs/${runId}/ratios${q}`);
  const facts = useApi<Row[]>(`/runs/${runId}/facts${q}`);
  const history = useApi<Row[]>(`/runs/${runId}/history${q}`);
  const flags = useApi<Row[]>(`/runs/${runId}/flags${q}`);
  const review = useApi<Row[]>(`/runs/${runId}/review${q}`);
  const loads = [run, screening, ratios, facts, history, flags, review];
  const ready = settled(...loads);
  const row = screening.data?.[0];
  const notApplicable = new Set(String(row?.["Not Applicable Metrics"] ?? "").split("; ").filter(Boolean));
  const lineage = ratios.data ?? [];
  const factById = new Map((facts.data ?? []).map((f) => [String(f["Fact ID"]), f]));
  const cited = new Map<string, Row>();
  for (const r of ratios.data ?? []) {
    for (const id of String(r["Input Fact IDs"] ?? "").split(";").map((x) => x.trim()).filter(Boolean)) {
      const fact = factById.get(id);
      if (fact) cited.set(id, fact);
    }
  }
  const years = [...new Set((history.data ?? []).map((h) => String(h["Financial Year End"])))].sort();

  return (
    <Shell ready={ready} error={firstError(...loads) ?? (ready && !row ? `${ticker} has no screening row in this run` : null)}>
      {run.data && row && (
        <>
          <Cover title={String(row.Company)} subtitle={`${ticker} · ${run.data.sector}, ${run.data.period}`} run={run.data} extra="Metrics with period basis, history, formulas and inputs, citations, flags" />
          <p>
            Data confidence: {String(row["Data Confidence"])} · Income basis {String(row["Income Period Basis"] ?? MISSING)} · Cash-flow basis {String(row["Cash Flow Period Basis"] ?? MISSING)} · Balance sheet {String(row["Balance Sheet Date"] ?? MISSING)}
          </p>
          {METRIC_GROUPS.map(([title, names]) => (
            <section key={title}>
              <Table
                caption={title}
                head={["Metric", "Value", "Period basis"]}
                numeric={[1]}
                rows={names
                  .filter((name) => name in row)
                  .map((name) => [
                    name,
                    notApplicable.has(name) ? "Not applicable" : formatValue(name, row[name]),
                    notApplicable.has(name) ? "—" : String(lineageRows(lineage, name)[0]?.["Period Basis"] ?? MISSING),
                  ])}
              />
            </section>
          ))}
          <section>
            <Table
              caption="Annual history (reconciled values)"
              head={["Metric", ...years.map((y) => y.slice(0, 4))]}
              numeric={years.map((_, i) => i + 1)}
              rows={HISTORY_METRICS.map((metric) => [
                metric,
                ...years.map((year) => {
                  const hit = (history.data ?? []).find((h) => h.Metric === metric && String(h["Financial Year End"]) === year);
                  return hit ? formatValue(metric === "eps" || metric === "dps" ? "EPS" : "Revenue", hit.Value) : MISSING;
                }),
              ])}
            />
          </section>
          <section>
            <Table
              caption="Calculations: formula, inputs and period basis"
              head={["Metric", "Value", "Formula", "Basis", "Input facts"]}
              numeric={[1]}
              rows={(ratios.data ?? []).map((r) => [
                String(r.Metric),
                formatExact(r.Value),
                String(r.Formula ?? MISSING),
                String(r["Period Basis"] ?? MISSING),
                <span key="i" className="break-all font-mono text-[9px]">{String(r["Input Fact IDs"] ?? "") || MISSING}</span>,
              ])}
            />
          </section>
          <section>
            <Table
              caption="Citations"
              head={["Fact", "Value", "Document", "Page", "Confidence"]}
              numeric={[1, 3]}
              rows={[...cited.entries()].map(([id, fact]) => {
                const parsed = parseFactId(id);
                return [
                  <span key="f" className="break-all font-mono text-[9px]">{parsed.metric || id}</span>,
                  `${formatExact(fact["Extracted Value"])} ${String(fact.Unit ?? "")}`,
                  String(fact["Source Document"] ?? MISSING),
                  String(toNumber(fact["Source Page"]) ?? MISSING),
                  String(fact["Extraction Confidence"] ?? MISSING),
                ];
              })}
            />
          </section>
          <section>
            <Table caption="Flags" head={["Flag", "Evidence"]} rows={(flags.data ?? []).map((f) => [String(f.Flag), String(f.Evidence ?? "")])} />
          </section>
          <section>
            <Table caption="Items under review" head={["Metric", "Reason", "Detail"]} rows={(review.data ?? []).map((r) => [String(r.Metric), String(r["Validation Rule"]), String(r["Reason for Uncertainty"] ?? "")])} />
          </section>
        </>
      )}
    </Shell>
  );
}

export function ReviewPrint({ runId }: { runId: string }) {
  const run = useApi<Run>(`/runs/${runId}`);
  const review = useApi<Row[]>(`/runs/${runId}/review`);
  const loads = [run, review];
  const ready = settled(...loads);
  return (
    <Shell ready={ready} error={firstError(...loads)}>
      {run.data && (
        <>
          <Cover title="Review pack" subtitle={`${run.data.sector}, ${run.data.period}`} run={run.data} extra={`${review.data?.length ?? 0} items, each with its source text and page`} />
          {(review.data ?? []).length === 0 && <p>No values were withheld or flagged in this run.</p>}
          {(review.data ?? []).map((item, index) => (
            <section key={index} className="break-inside-avoid space-y-1 border-b border-line pb-3">
              <h2 className="text-sm font-medium">
                {index + 1}. {String(item.Company)} ({String(item.Ticker)}) · {String(item.Metric)} · {String(item["Financial Period"] ?? "").slice(0, 10) || MISSING}
              </h2>
              <p className="text-muted">{String(item["Validation Rule"])}</p>
              <p>{String(item["Reason for Uncertainty"] ?? "")}</p>
              {item["Candidate Values"] ? <p>Candidate values: {String(item["Candidate Values"])}</p> : null}
              <p className="text-muted">
                {String(item["Source Document"] || "No source document")} · page {String(toNumber(item["Source Page"]) ?? MISSING)} · {String(item["Extraction Strategy"] ?? "")}
              </p>
              {item["Source Text"] ? <p className="rounded border border-line bg-bg p-2 font-mono text-[10px] break-words">{String(item["Source Text"])}</p> : null}
            </section>
          ))}
        </>
      )}
    </Shell>
  );
}
