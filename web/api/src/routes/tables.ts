import fs from "node:fs";
import path from "node:path";
import { Router } from "express";
import type { JobQueue } from "../jobs.js";
import { ID_PATTERN, TICKER_PATTERN } from "../validation.js";

/** URL name -> file written by `export_json` in the Python package. */
export const TABLES: Record<string, string> = {
  universe: "universe.json",
  screening: "screening.json",
  facts: "raw_facts.json",
  ratios: "ratios.json",
  history: "history.json",
  dividends: "dividends.json",
  sources: "sources.json",
  flags: "flags.json",
  review: "review.json",
  summary: "summary.json",
};

/**
 * Serves the Python run directory as it is. Nothing here calculates a value: the
 * rows are the pipeline's own output, optionally narrowed to one ticker.
 */
export function tablesRouter(queue: JobQueue): Router {
  const router = Router();

  router.get("/runs/:id/:table", (req, res, next) => {
    const file = Object.hasOwn(TABLES, req.params.table) ? TABLES[req.params.table] : undefined;
    if (!file) {
      next();
      return;
    }
    const run = ID_PATTERN.test(req.params.id) ? queue.getRun(req.params.id) : undefined;
    if (!run) {
      res.status(404).json({ error: "not_found" });
      return;
    }
    const ticker = typeof req.query.ticker === "string" ? req.query.ticker : undefined;
    if (ticker !== undefined && !TICKER_PATTERN.test(ticker)) {
      res.status(400).json({ error: "invalid_request", message: "ticker must look like ACL.N0000" });
      return;
    }
    const location = path.join(run.run_dir, file);
    if (!fs.existsSync(location)) {
      res.status(409).json({ error: "not_ready", message: `Run is ${run.status}; no ${req.params.table} table yet.` });
      return;
    }
    let rows = JSON.parse(fs.readFileSync(location, "utf-8")) as Record<string, unknown>[];
    if (ticker) {
      rows = rows.filter((row) => row.Ticker === ticker);
    }
    res.json(rows);
  });

  return router;
}
