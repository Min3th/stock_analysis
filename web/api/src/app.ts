import express from "express";
import type { Config } from "./config.js";
import type { Db } from "./db.js";
import type { JobQueue } from "./jobs.js";
import { pythonRunner, type PythonRunner } from "./python.js";
import { correctionsRouter } from "./routes/corrections.js";
import { documentsRouter } from "./routes/documents.js";
import { healthRouter } from "./routes/health.js";
import { runsRouter } from "./routes/runs.js";
import { tablesRouter } from "./routes/tables.js";
import { universeRouter } from "./routes/universe.js";
import { uploadsRouter } from "./routes/uploads.js";

export interface Deps {
  python?: PythonRunner;
}

export function createApp(
  config: Config,
  db: Db,
  queue: JobQueue,
  deps: Deps = {},
): express.Express {
  const app = express();
  app.disable("x-powered-by");

  // CORS is limited to the Next.js origin(s); any other origin gets no CORS headers.
  app.use((req, res, next) => {
    const origin = req.headers.origin;
    if (origin && config.allowedOrigins.includes(origin)) {
      res.setHeader("Access-Control-Allow-Origin", origin);
      res.setHeader("Vary", "Origin");
      res.setHeader("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS");
      res.setHeader("Access-Control-Allow-Headers", "Content-Type");
    }
    if (req.method === "OPTIONS") {
      res.sendStatus(204);
      return;
    }
    next();
  });

  app.use(express.json({ limit: "1mb" }));
  app.use("/api", healthRouter(config, db));
  app.use("/api", universeRouter(config));
  app.use("/api", runsRouter(queue));
  app.use("/api", tablesRouter(queue));
  app.use("/api", documentsRouter(config, queue));
  const python = deps.python ?? pythonRunner(config);
  app.use("/api", uploadsRouter(config, db, python));
  app.use("/api", correctionsRouter(db, python));

  app.use("/api", (_req, res) => {
    res.status(404).json({ error: "not_found" });
  });
  app.use((err: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    if ((err as { code?: string }).code === "LIMIT_FILE_SIZE") {
      res.status(413).json({ error: "upload_failed", message: "The file is larger than the upload limit." });
      return;
    }
    if (err instanceof SyntaxError) {
      res.status(400).json({ error: "invalid_json" });
      return;
    }
    const message = err instanceof Error ? err.message : "unexpected error";
    res.status(500).json({ error: "internal_error", message });
  });
  return app;
}
