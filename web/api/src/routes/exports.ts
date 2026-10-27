import { Router } from "express";
import type { JobQueue } from "../jobs.js";
import type { PdfRenderer } from "../pdf.js";
import { ID_PATTERN, TICKER_PATTERN, ValidationError } from "../validation.js";

const TYPES = ["sector", "company", "review"] as const;
type ExportType = (typeof TYPES)[number];

/** The print route and file name for an export; every part has been validated first. */
export function exportTarget(type: ExportType, runId: string, ticker?: string) {
  const encoded = encodeURIComponent(runId);
  if (type === "company") {
    return {
      path: `/print/company/${encoded}/${encodeURIComponent(ticker as string)}`,
      landscape: false,
      filename: `${ticker}_${runId}.pdf`,
    };
  }
  return {
    path: `/print/${type}/${encoded}`,
    landscape: type === "sector",
    filename: `${type === "sector" ? "Sector_report" : "Review_pack"}_${runId}.pdf`,
  };
}

export function exportsRouter(queue: JobQueue, renderer: PdfRenderer): Router {
  const router = Router();

  router.post("/exports", async (req, res, next) => {
    try {
      const body = (req.body ?? {}) as Record<string, unknown>;
      const type = body.type as ExportType;
      if (!TYPES.includes(type)) throw new ValidationError("type must be sector, company or review");
      const runId = String(body.runId ?? "");
      if (!ID_PATTERN.test(runId)) throw new ValidationError("runId is not valid");
      let ticker: string | undefined;
      if (type === "company") {
        ticker = String(body.ticker ?? "");
        if (!TICKER_PATTERN.test(ticker)) throw new ValidationError("ticker must look like ACL.N0000");
      }
      const run = queue.getRun(runId);
      if (!run) {
        res.status(404).json({ error: "not_found", message: "No such run." });
        return;
      }
      if (run.status !== "ok" && run.status !== "empty") {
        res.status(409).json({ error: "not_ready", message: `The run is ${run.status}; export it once it has completed.` });
        return;
      }
      const target = exportTarget(type, runId, ticker);
      let pdf: Buffer;
      try {
        pdf = await renderer.render(target.path, { landscape: target.landscape });
      } catch (error) {
        res.status(502).json({ error: "render_failed", message: `The PDF could not be rendered: ${(error as Error).message.split("\n")[0]}` });
        return;
      }
      res.setHeader("Content-Type", "application/pdf");
      res.setHeader("Content-Disposition", `attachment; filename="${target.filename}"`);
      res.setHeader("X-Content-Type-Options", "nosniff");
      res.send(pdf);
    } catch (error) {
      if (error instanceof ValidationError) {
        res.status(400).json({ error: "invalid_request", message: error.message });
        return;
      }
      next(error);
    }
  });

  return router;
}
