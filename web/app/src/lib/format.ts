/** The pipeline writes decimals as strings so no precision is lost; display code parses them. */
export type Cell = string | number | boolean | null | undefined;
export type Row = Record<string, Cell>;

export function toNumber(value: Cell): number | null {
  if (value === null || value === undefined || value === "" || typeof value === "boolean") {
    return null;
  }
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

type Kind = "money" | "percent" | "multiple" | "perShare" | "count" | "text";

/** How each screening column is shown. Only presentation: values are never changed. */
export const COLUMN_KIND: Record<string, Kind> = {
  "Current Price": "perShare",
  "Market Cap": "money",
  Revenue: "money",
  "Revenue Growth YoY": "percent",
  "Net Profit": "money",
  EPS: "perShare",
  "EPS Growth YoY": "percent",
  "3Y Revenue CAGR": "percent",
  "3Y EPS CAGR": "percent",
  ROE: "percent",
  ROA: "percent",
  "Debt-to-Equity": "multiple",
  "Debt-to-Equity incl. Leases": "multiple",
  "Net Debt": "money",
  "Operating Cash Flow": "money",
  "Free Cash Flow": "money",
  "OCF / Net Profit": "multiple",
  "P/E": "multiple",
  "P/B": "multiple",
  DPS: "perShare",
  "Dividend Yield": "percent",
  "Payout Ratio": "percent",
  "Earnings Yield": "percent",
  "Net Profit Growth YoY": "percent",
  "Operating Profit": "money",
  EBIT: "money",
  "Book Value Per Share": "perShare",
  "Ordinary Shares Outstanding": "count",
  "Listed Class Shares": "count",
  "Retained Earnings": "money",
  "Lease Liabilities": "money",
  "Recent Volume": "count",
  "Average Daily Volume": "count",
  "Median Daily Volume": "count",
  "Liquidity Trading Days": "count",
};

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 });
const grouped = new Intl.NumberFormat("en", { maximumFractionDigits: 0 });
const two = new Intl.NumberFormat("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const MISSING = "—";

export function formatValue(column: string, value: Cell): string {
  const kind = COLUMN_KIND[column] ?? "text";
  const number = toNumber(value);
  if (kind === "text" || number === null) {
    return value === null || value === undefined || value === "" ? MISSING : String(value);
  }
  switch (kind) {
    case "money":
      return `${number < 0 ? "−" : ""}${compact.format(Math.abs(number))}`;
    case "percent":
      return `${(number * 100).toFixed(1)}%`;
    case "multiple":
      return `${two.format(number)}×`;
    case "perShare":
      return two.format(number);
    case "count":
      return grouped.format(number);
  }
}

/** Exact value for a tooltip or lineage table (no rounding beyond the stored digits). */
export function formatExact(value: Cell): string {
  const number = toNumber(value);
  if (number === null) {
    return value === null || value === undefined || value === "" ? MISSING : String(value);
  }
  return Number.isInteger(number) ? grouped.format(number) : String(Number(number.toPrecision(10)));
}

export const CONFIDENCE_LABEL: Record<string, string> = {
  high: "Passed checks",
  review: "Needs review",
  low: "Low confidence",
};
