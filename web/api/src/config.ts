import path from "node:path";
import { fileURLToPath } from "node:url";

export interface Config {
  host: "127.0.0.1";
  port: number;
  pythonBin: string;
  repoRoot: string;
  dataDir: string;
  dbPath: string;
  allowedOrigins: string[];
  uploadLimitBytes: number;
  /** Where the Next.js app is served; PDF exports render its /print routes. */
  webUrl: string;
}

const here = path.dirname(fileURLToPath(import.meta.url));

/** Settings come from the environment (web/.env is loaded by `node --env-file`). */
export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const webRoot = path.resolve(here, "..", "..");
  const repoRoot = path.resolve(webRoot, env.REPO_ROOT ?? "..");
  const dataDir = path.resolve(webRoot, env.WEB_DATA_DIR ?? "./data");
  const port = Number(env.API_PORT ?? 4000);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`API_PORT must be a port number, got ${env.API_PORT}`);
  }
  const limitMb = Number(env.UPLOAD_LIMIT_MB ?? 50);
  return {
    // The API is for this machine only; it never binds another interface.
    host: "127.0.0.1",
    port,
    pythonBin: env.PYTHON_BIN ?? "python",
    repoRoot,
    dataDir,
    dbPath: path.join(dataDir, "web.sqlite"),
    allowedOrigins: (env.WEB_ORIGIN ?? "http://127.0.0.1:3000,http://localhost:3000")
      .split(",")
      .map((origin) => origin.trim())
      .filter(Boolean),
    uploadLimitBytes: Math.max(1, limitMb) * 1024 * 1024,
    webUrl: env.WEB_URL ?? "http://127.0.0.1:3000",
  };
}
