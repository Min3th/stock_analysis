import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { Router } from "express";
import multer from "multer";
import type { Config } from "../config.js";
import type { Db } from "../db.js";
import type { PythonRunner } from "../python.js";
import { ID_PATTERN, TICKER_PATTERN } from "../validation.js";

const KINDS = ["annual_report", "interim_statement"] as const;
const DATE = /^\d{4}-\d{2}-\d{2}$/;

interface UploadRow {
  id: string;
  ticker: string;
  kind: (typeof KINDS)[number];
  period_end: string;
  period_months: number | null;
  original_filename: string;
  sha256: string;
  stored_path: string;
  status: "pending" | "accepted" | "rejected";
  preview_json: string | null;
  created_at: string;
  decided_at: string | null;
}

const present = (row: UploadRow) => ({
  id: row.id,
  ticker: row.ticker,
  kind: row.kind,
  periodEnd: row.period_end,
  periodMonths: row.period_months,
  originalFilename: row.original_filename,
  sha256: row.sha256,
  status: row.status,
  preview: row.preview_json ? (JSON.parse(row.preview_json) as unknown) : null,
  createdAt: row.created_at,
  decidedAt: row.decided_at,
});

function fail(res: import("express").Response, status: number, error: string, message: string) {
  res.status(status).json({ error, message });
}

export function uploadsRouter(config: Config, db: Db, python: PythonRunner): Router {
  const router = Router();
  const pendingDir = path.join(config.dataDir, "uploads", "pending");
  fs.mkdirSync(pendingDir, { recursive: true });
  // Client file names are never used as paths: the temporary name is random.
  const upload = multer({
    storage: multer.diskStorage({
      destination: pendingDir,
      filename: (_req, _file, cb) => cb(null, `${crypto.randomUUID()}.part`),
    }),
    limits: { fileSize: config.uploadLimitBytes, files: 1 },
  });

  const get = (id: string) =>
    (ID_PATTERN.test(id) ? db.prepare("SELECT * FROM uploads WHERE id = ?").get(id) : undefined) as
      | UploadRow
      | undefined;

  router.get("/uploads", (_req, res) => {
    const rows = db.prepare("SELECT * FROM uploads ORDER BY created_at DESC LIMIT 100").all() as UploadRow[];
    res.json(rows.map(present));
  });

  router.get("/uploads/:id", (req, res) => {
    const row = get(req.params.id);
    if (!row) return fail(res, 404, "not_found", "No such upload");
    res.json(present(row));
  });

  router.post("/uploads", (req, res, next) => {
    upload.single("file")(req, res, async (error: unknown) => {
      const temp = req.file?.path;
      const discard = () => temp && fs.rmSync(temp, { force: true });
      try {
        if (error) {
          discard();
          const tooBig = (error as { code?: string }).code === "LIMIT_FILE_SIZE";
          return fail(res, tooBig ? 413 : 400, "upload_failed", tooBig ? "The file is larger than the upload limit." : "The upload could not be read.");
        }
        const { ticker, kind, periodEnd } = req.body as Record<string, string | undefined>;
        const months = req.body.periodMonths ? Number(req.body.periodMonths) : null;
        if (!req.file || !temp) return fail(res, 400, "invalid_request", "Choose a PDF file.");
        if (!ticker || !TICKER_PATTERN.test(ticker)) {
          discard();
          return fail(res, 400, "invalid_request", "ticker must look like ACL.N0000");
        }
        if (!kind || !KINDS.includes(kind as (typeof KINDS)[number])) {
          discard();
          return fail(res, 400, "invalid_request", "kind must be annual_report or interim_statement");
        }
        if (!periodEnd || !DATE.test(periodEnd) || Number.isNaN(Date.parse(periodEnd))) {
          discard();
          return fail(res, 400, "invalid_request", "periodEnd must look like 2026-03-31");
        }
        if (kind === "interim_statement" && (!months || !Number.isInteger(months) || months < 1 || months > 11)) {
          discard();
          return fail(res, 400, "invalid_request", "An interim statement needs periodMonths from 1 to 11.");
        }
        const content = fs.readFileSync(temp);
        if (!content.subarray(0, 4).equals(Buffer.from("%PDF"))) {
          discard();
          return fail(res, 400, "not_a_pdf", "The file is not a PDF (it does not start with %PDF).");
        }
        const sha256 = crypto.createHash("sha256").update(content).digest("hex");
        const stored = path.join(pendingDir, `${sha256.slice(0, 16)}.pdf`);
        fs.renameSync(temp, stored);

        const extractArgs = ["extract", "--pdf", stored, "--kind", kind, "--period-end", periodEnd];
        if (months) extractArgs.push("--period-months", String(months));
        const result = await python(extractArgs);
        if (result.code !== 0) {
          fs.rmSync(stored, { force: true });
          return fail(res, 422, "extraction_failed", result.stderr.trim().split("\n").slice(-3).join(" ") || "The extractor could not read this PDF.");
        }
        let preview: unknown;
        try {
          // Libraries may print a notice before the JSON document starts.
          preview = JSON.parse(result.stdout.slice(Math.max(0, result.stdout.search(/^\{/m))));
        } catch {
          fs.rmSync(stored, { force: true });
          return fail(res, 422, "extraction_failed", "The extractor returned unreadable output.");
        }
        const id = crypto.randomUUID();
        db.prepare(
          `INSERT INTO uploads (id, ticker, kind, period_end, period_months, original_filename, sha256,
             stored_path, status, preview_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)`,
        ).run(id, ticker, kind, periodEnd, months, path.basename(req.file.originalname), sha256, stored, JSON.stringify(preview), new Date().toISOString());
        res.status(201).json(present(get(id) as UploadRow));
      } catch (caught) {
        discard();
        next(caught);
      }
    });
  });

  router.post("/uploads/:id/accept", async (req, res, next) => {
    try {
      const row = get(req.params.id);
      if (!row) return fail(res, 404, "not_found", "No such upload");
      if (row.status !== "pending") return fail(res, 409, "not_pending", `This upload was already ${row.status}.`);
      const title = typeof req.body?.title === "string" && req.body.title.trim() ? req.body.title.trim().slice(0, 200) : row.original_filename;
      const args = ["uploads", "add", "--pdf", row.stored_path, "--ticker", row.ticker, "--kind", row.kind, "--period-end", row.period_end, "--title", title, "--original-name", row.original_filename];
      if (row.period_months) args.push("--period-months", String(row.period_months));
      const result = await python(args);
      if (result.code !== 0) {
        // Python is the only writer of config/uploads.yml and also checks the universe.
        return fail(res, 422, "rejected_by_pipeline", result.stderr.trim().split("\n").slice(-2).join(" ") || "The pipeline did not accept this upload.");
      }
      db.prepare("UPDATE uploads SET status = 'accepted', decided_at = ? WHERE id = ?").run(new Date().toISOString(), row.id);
      fs.rmSync(row.stored_path, { force: true });
      res.json(present(get(row.id) as UploadRow));
    } catch (error) {
      next(error);
    }
  });

  router.delete("/uploads/:id", (req, res) => {
    const row = get(req.params.id);
    if (!row) return fail(res, 404, "not_found", "No such upload");
    if (row.status !== "pending") return fail(res, 409, "not_pending", `This upload was already ${row.status}.`);
    fs.rmSync(row.stored_path, { force: true });
    db.prepare("UPDATE uploads SET status = 'rejected', decided_at = ? WHERE id = ?").run(new Date().toISOString(), row.id);
    res.json(present(get(row.id) as UploadRow));
  });

  return router;
}
