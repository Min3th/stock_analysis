import fs from "node:fs";
import path from "node:path";
import { Router } from "express";
import type { Config } from "../config.js";
import type { JobQueue } from "../jobs.js";
import { ID_PATTERN, TICKER_PATTERN } from "../validation.js";

const DOCUMENT_ID = /^[0-9a-f]{16}$/;

interface SourceRow {
  Ticker?: string;
  "Document ID"?: string;
  "Local Path"?: string;
  Document?: string;
}

/** True when `child` is inside `parent` (after resolving), so a recorded path cannot escape the cache. */
export function isInside(parent: string, child: string): boolean {
  const relative = path.relative(path.resolve(parent), path.resolve(child));
  return relative !== "" && !relative.startsWith("..") && !path.isAbsolute(relative);
}

export function documentsRouter(config: Config, queue: JobQueue): Router {
  const router = Router();
  const cacheRoot = path.join(config.repoRoot, "data", "raw");

  /** Source rows of one run, or of every finished run from newest to oldest. */
  function sourceRows(runId?: string): SourceRow[] {
    const runs = runId ? [queue.getRun(runId)] : queue.listRuns(50);
    const rows: SourceRow[] = [];
    for (const run of runs) {
      const file = run ? path.join(run.run_dir, "sources.json") : "";
      if (file && fs.existsSync(file)) {
        rows.push(...(JSON.parse(fs.readFileSync(file, "utf-8")) as SourceRow[]));
      }
    }
    return rows;
  }

  // The cached PDF behind a cited fact, so the viewer can open it at the cited page.
  router.get("/documents/:ticker/:docId/file", (req, res) => {
    const { ticker, docId } = req.params;
    const run = typeof req.query.run === "string" ? req.query.run : undefined;
    if (!TICKER_PATTERN.test(ticker) || !DOCUMENT_ID.test(docId) || (run && !ID_PATTERN.test(run))) {
      res.status(400).json({ error: "invalid_request" });
      return;
    }
    const row = sourceRows(run).find(
      (item) => item.Ticker === ticker && item["Document ID"] === docId && item["Local Path"],
    );
    const location = row?.["Local Path"];
    // Only files the pipeline itself cached are served, never an arbitrary path.
    if (!location || !isInside(cacheRoot, location) || !fs.existsSync(location)) {
      res.status(404).json({ error: "not_found" });
      return;
    }
    res.setHeader("Content-Type", "application/pdf");
    res.setHeader("Content-Disposition", "inline");
    res.setHeader("X-Content-Type-Options", "nosniff");
    fs.createReadStream(location).pipe(res);
  });

  return router;
}
