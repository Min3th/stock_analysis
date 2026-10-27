import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createApp } from "../src/app.js";
import { loadConfig, type Config } from "../src/config.js";
import { openDb, type Db } from "../src/db.js";
import { JobQueue, type CommandBuilder } from "../src/jobs.js";

export interface Harness {
  config: Config;
  db: Db;
  queue: JobQueue;
  app: ReturnType<typeof createApp>;
  root: string;
}

/** A stand-in for `python main.py run ...`: a short Node script run with an argument array. */
export function stubPipeline(script: string): CommandBuilder {
  return (request, runDir) => ({
    bin: process.execPath,
    args: ["-e", script, runDir, JSON.stringify(request)],
    cwd: os.tmpdir(),
  });
}

export const WRITE_MANIFEST = (status: string) => `
const fs = require('fs'), path = require('path');
const dir = process.argv[1];
console.log('stub run started');
console.log('xlsx: ' + path.join(dir, 'x.xlsx'));
fs.mkdirSync(dir, { recursive: true });
fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify({
  status: '${status}', git_commit: 'abc123', config_hash: 'hash42',
  counts: { screening: 3, review: 5 },
}));
`;

export function harness(build?: CommandBuilder, env: NodeJS.ProcessEnv = {}): Harness {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "cse-web-"));
  fs.mkdirSync(path.join(root, "repo"), { recursive: true });
  fs.writeFileSync(path.join(root, "repo", "main.py"), "# stub\n");
  const config = loadConfig({
    REPO_ROOT: path.join(root, "repo"),
    WEB_DATA_DIR: path.join(root, "data"),
    ...env,
  });
  const db = openDb(":memory:");
  const queue = new JobQueue(config, db, build);
  return { config, db, queue, app: createApp(config, db, queue), root };
}
