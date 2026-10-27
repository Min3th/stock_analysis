import crypto from "node:crypto";
import { Router } from "express";
import type { Db } from "../db.js";
import type { PythonRunner } from "../python.js";
import { ID_PATTERN, TICKER_PATTERN, ValidationError } from "../validation.js";

const UNITS = ["LKR", "LKR '000", "LKR million", "LKR billion", "LKR/share", "shares", "ratio"];
const SCOPES = ["group", "company", "primary", "unknown"];
const METRIC = /^[a-z][a-z_]{1,39}$/;
const NUMBER = /^-?\d{1,20}(\.\d{1,10})?$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const CORRECTION_ID = /^[A-Za-z0-9._-]{1,120}$/;

export interface CorrectionInput {
  ticker: string;
  metric: string;
  value: string;
  unit: string;
  periodEnd: string;
  document: string;
  sourcePage: number;
  scope: string;
  reason: string;
  author: string;
  sourceText?: string;
  supersedes?: string;
}

const text = (value: unknown, name: string, min: number, max: number): string => {
  if (typeof value !== "string") throw new ValidationError(`${name} is required`);
  const clean = value.replace(/[\r\n]+/g, " ").trim();
  if (clean.length < min || clean.length > max) {
    throw new ValidationError(`${name} must be ${min} to ${max} characters`);
  }
  return clean;
};

export function parseCorrection(body: unknown): CorrectionInput {
  if (typeof body !== "object" || body === null) throw new ValidationError("A JSON body is required");
  const input = body as Record<string, unknown>;
  const ticker = String(input.ticker ?? "");
  if (!TICKER_PATTERN.test(ticker)) throw new ValidationError("ticker must look like ACL.N0000");
  const metric = String(input.metric ?? "");
  if (!METRIC.test(metric)) throw new ValidationError("metric must be a pipeline metric name such as net_profit");
  const value = String(input.value ?? "").trim().replace(/,/g, "");
  if (!NUMBER.test(value)) throw new ValidationError("value must be a plain number, for example 1250.5 or -300");
  const unit = String(input.unit ?? "");
  if (!UNITS.includes(unit)) throw new ValidationError(`unit must be one of: ${UNITS.join(", ")}`);
  const periodEnd = String(input.periodEnd ?? "");
  if (!DATE.test(periodEnd) || Number.isNaN(Date.parse(periodEnd))) throw new ValidationError("periodEnd must look like 2026-03-31");
  const sourcePage = Number(input.sourcePage);
  if (!Number.isInteger(sourcePage) || sourcePage < 1 || sourcePage > 5000) throw new ValidationError("sourcePage must be a page number of 1 or more");
  const scope = String(input.scope ?? "group");
  if (!SCOPES.includes(scope)) throw new ValidationError(`scope must be one of: ${SCOPES.join(", ")}`);
  const supersedes = input.supersedes === undefined || input.supersedes === "" ? undefined : String(input.supersedes);
  if (supersedes !== undefined && !CORRECTION_ID.test(supersedes)) throw new ValidationError("supersedes is not a valid correction id");
  return {
    ticker,
    metric,
    value,
    unit,
    periodEnd,
    document: text(input.document, "document", 3, 300),
    sourcePage,
    scope,
    reason: text(input.reason, "reason", 5, 500),
    author: input.author === undefined || input.author === "" ? "reviewer" : text(input.author, "author", 1, 60),
    sourceText: input.sourceText === undefined || input.sourceText === "" ? undefined : text(input.sourceText, "sourceText", 1, 1000),
    supersedes,
  };
}

/** `--flag=value` keeps any value, even one starting with "-", from being read as an option. */
export function correctionArgs(c: CorrectionInput): string[] {
  const args = [
    "corrections",
    "add",
    `--ticker=${c.ticker}`,
    `--metric=${c.metric}`,
    `--value=${c.value}`,
    `--unit=${c.unit}`,
    `--period-end=${c.periodEnd}`,
    `--document=${c.document}`,
    `--source-page=${c.sourcePage}`,
    `--scope=${c.scope}`,
    `--reason=${c.reason}`,
    `--author=${c.author}`,
  ];
  if (c.sourceText) args.push(`--source-text=${c.sourceText}`);
  if (c.supersedes) args.push(`--supersedes=${c.supersedes}`);
  return args;
}

interface LogRow {
  id: string;
  correction_id: string | null;
  ticker: string;
  metric: string;
  payload_json: string;
  created_at: string;
}

export function correctionsRouter(db: Db, python: PythonRunner): Router {
  const router = Router();

  router.post("/corrections", async (req, res, next) => {
    try {
      const correction = parseCorrection(req.body);
      const result = await python(correctionArgs(correction));
      const match = /^correction:\s*(\S+)/m.exec(result.stdout);
      if (result.code !== 0 || !match) {
        // Python validates the whole file and the supersede target; its message is the reason.
        const message = result.stderr.trim().split("\n").slice(-2).join(" ") || "The pipeline did not accept this correction.";
        res.status(422).json({ error: "rejected_by_pipeline", message });
        return;
      }
      const correctionId = match[1] as string;
      db.prepare(
        "INSERT INTO corrections_log (id, correction_id, ticker, metric, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
      ).run(crypto.randomUUID(), correctionId, correction.ticker, correction.metric, JSON.stringify(correction), new Date().toISOString());
      res.status(201).json({
        correctionId,
        note: "Stored in config/corrections.yml. It is applied the next time this company is run; nothing already published changes.",
      });
    } catch (error) {
      if (error instanceof ValidationError) {
        res.status(400).json({ error: "invalid_request", message: error.message });
        return;
      }
      next(error);
    }
  });

  // Corrections submitted from this app, newest first, with whether a later one replaced them.
  router.get("/corrections", (req, res) => {
    const ticker = typeof req.query.ticker === "string" ? req.query.ticker : undefined;
    const metric = typeof req.query.metric === "string" ? req.query.metric : undefined;
    if ((ticker && !TICKER_PATTERN.test(ticker)) || (metric && !METRIC.test(metric)) || (req.query.run && !ID_PATTERN.test(String(req.query.run)))) {
      res.status(400).json({ error: "invalid_request" });
      return;
    }
    const rows = db.prepare("SELECT * FROM corrections_log ORDER BY created_at DESC, rowid DESC").all() as LogRow[];
    const replaced = new Set(
      rows.map((row) => (JSON.parse(row.payload_json) as CorrectionInput).supersedes).filter((id): id is string => Boolean(id)),
    );
    res.json(
      rows
        .filter((row) => (!ticker || row.ticker === ticker) && (!metric || row.metric === metric))
        .map((row) => ({
          correctionId: row.correction_id,
          createdAt: row.created_at,
          superseded: row.correction_id !== null && replaced.has(row.correction_id),
          ...(JSON.parse(row.payload_json) as CorrectionInput),
        })),
    );
  });

  return router;
}
