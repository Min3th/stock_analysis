import { GROUP_NAMES } from "./universe.js";

/** Same pattern the pipeline's tickers follow, for example ACL.N0000 or COMB.X0000. */
export const TICKER_PATTERN = /^[A-Z]+\.[NXRWP]\d{4}$/;
/** An output label such as 2026Q3 or 2026. */
export const PERIOD_PATTERN = /^(20\d{2})(Q[1-4])?$/;
/** Run and job ids are generated here; anything else is refused before it reaches a path. */
export const ID_PATTERN = /^[A-Za-z0-9_-]{1,100}$/;

export interface RunRequest {
  sector: string;
  period: string;
  ticker?: string;
  offline: boolean;
}

export class ValidationError extends Error {}

/**
 * Every value that reaches `spawn` is checked here first: the sector against an
 * allow-list, the ticker and period against strict patterns. Nothing is passed
 * through a shell, and arguments are always an array.
 */
export function parseRunRequest(body: unknown): RunRequest {
  if (typeof body !== "object" || body === null) {
    throw new ValidationError("A JSON body is required");
  }
  const input = body as Record<string, unknown>;
  const sector = input.sector;
  if (typeof sector !== "string" || !GROUP_NAMES.includes(sector)) {
    throw new ValidationError("sector must be one of the supported CSE industry groups");
  }
  const period = typeof input.period === "string" ? input.period.toUpperCase() : undefined;
  if (period === undefined || !PERIOD_PATTERN.test(period)) {
    throw new ValidationError("period must look like 2026Q3 or 2026");
  }
  let ticker: string | undefined;
  if (input.ticker !== undefined && input.ticker !== null && input.ticker !== "") {
    if (typeof input.ticker !== "string" || !TICKER_PATTERN.test(input.ticker)) {
      throw new ValidationError("ticker must look like ACL.N0000");
    }
    ticker = input.ticker;
  }
  if (input.offline !== undefined && typeof input.offline !== "boolean") {
    throw new ValidationError("offline must be true or false");
  }
  return { sector, period, ticker, offline: input.offline === true };
}
