import fs from "node:fs";
import path from "node:path";
import { Router } from "express";
import type { Config } from "../config.js";
import type { Db } from "../db.js";

export function healthRouter(config: Config, db: Db): Router {
  const router = Router();
  router.get("/health", (_req, res) => {
    const tables = (
      db.prepare("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").all() as {
        name: string;
      }[]
    ).map((row) => row.name);
    res.json({
      status: "ok",
      host: config.host,
      port: config.port,
      repoRoot: config.repoRoot,
      pipelineFound: fs.existsSync(path.join(config.repoRoot, "main.py")),
      pythonBin: config.pythonBin,
      tables,
    });
  });
  return router;
}
