import express from "express";
import type { Config } from "./config.js";
import type { Db } from "./db.js";
import { healthRouter } from "./routes/health.js";

export function createApp(config: Config, db: Db): express.Express {
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

  app.use("/api", (_req, res) => {
    res.status(404).json({ error: "not_found" });
  });
  app.use((err: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    const message = err instanceof Error ? err.message : "unexpected error";
    res.status(500).json({ error: "internal_error", message });
  });
  return app;
}
