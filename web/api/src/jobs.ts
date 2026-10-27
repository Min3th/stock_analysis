import { spawn, type ChildProcess } from "node:child_process";
import { EventEmitter } from "node:events";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import type { Config } from "./config.js";
import type { Db } from "./db.js";
import { groupSlug } from "./universe.js";
import type { RunRequest } from "./validation.js";

export interface CommandSpec {
  bin: string;
  args: string[];
  cwd: string;
}

export type CommandBuilder = (request: RunRequest, runDir: string) => CommandSpec;

export interface RunEvent {
  seq: number;
  type: "log" | "status";
  data: string;
}

export interface RunRow {
  id: string;
  sector: string;
  period: string;
  ticker: string | null;
  offline: number;
  status: "queued" | "running" | "ok" | "empty" | "failed";
  run_dir: string;
  git_commit: string | null;
  config_hash: string | null;
  counts_json: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

const FINISHED = new Set(["ok", "empty", "failed"]);

/** `python main.py run ...` with an argument array; no shell is ever involved. */
export function pythonCommand(config: Config): CommandBuilder {
  return (request, runDir) => ({
    bin: config.pythonBin,
    args: [
      "main.py",
      "run",
      "--sector",
      request.sector,
      "--period",
      request.period,
      ...(request.ticker ? ["--company", request.ticker] : []),
      ...(request.offline ? ["--offline"] : []),
      "--run-dir",
      runDir,
    ],
    cwd: config.repoRoot,
  });
}

/**
 * A single-worker queue: runs are processed one at a time, in order, because the
 * pipeline shares one on-disk cache. Progress is the process output, kept in a
 * log file so it can be replayed to a viewer that connects late or after a restart.
 */
export class JobQueue {
  private readonly bus = new EventEmitter();
  private readonly counters = new Map<string, number>();
  private current: ChildProcess | null = null;
  private pumping = false;

  constructor(
    private readonly config: Config,
    private readonly db: Db,
    private readonly build: CommandBuilder = pythonCommand(config),
  ) {
    this.bus.setMaxListeners(50);
    this.recover();
  }

  /** Anything still queued or running when the server last stopped cannot be resumed. */
  private recover(): void {
    const now = new Date().toISOString();
    const message = "The server stopped before this run finished.";
    this.db
      .prepare(
        "UPDATE runs SET status = 'failed', error = ?, finished_at = ? WHERE status IN ('queued','running')",
      )
      .run(message, now);
    this.db
      .prepare(
        "UPDATE jobs SET status = 'failed', finished_at = ? WHERE status IN ('queued','running')",
      )
      .run(now);
  }

  enqueue(request: RunRequest): { runId: string; jobId: string } {
    const stamp = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14);
    const runId = `${stamp}-${groupSlug(request.sector)}-${request.period}-${crypto.randomBytes(2).toString("hex")}`;
    const jobId = crypto.randomUUID();
    const runDir = path.join(this.config.repoRoot, "data", "runs", runId);
    const logPath = this.logPath(runId);
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    fs.writeFileSync(logPath, "");
    const now = new Date().toISOString();
    this.db
      .prepare(
        `INSERT INTO runs (id, sector, period, ticker, offline, status, run_dir, created_at)
         VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)`,
      )
      .run(runId, request.sector, request.period, request.ticker ?? null, request.offline ? 1 : 0, runDir, now);
    this.db
      .prepare(
        `INSERT INTO jobs (id, run_id, status, args_json, log_path, created_at)
         VALUES (?, ?, 'queued', ?, ?, ?)`,
      )
      .run(jobId, runId, JSON.stringify(request), logPath, now);
    this.counters.set(runId, 0);
    this.emit(runId, "status", "queued");
    void this.pump();
    return { runId, jobId };
  }

  getRun(runId: string): RunRow | undefined {
    return this.db.prepare("SELECT * FROM runs WHERE id = ?").get(runId) as RunRow | undefined;
  }

  listRuns(limit = 100): RunRow[] {
    return this.db
      .prepare("SELECT * FROM runs ORDER BY created_at DESC, id DESC LIMIT ?")
      .all(limit) as RunRow[];
  }

  /** Resolves when no job is queued or running (used by tests and shutdown). */
  async idle(): Promise<void> {
    while (this.pumping || this.current) {
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
  }

  /**
   * Replays the stored log, then streams new events. Events carry a sequence
   * number so a line is never delivered twice across the replay/live boundary.
   */
  subscribe(runId: string, onEvent: (event: RunEvent) => void): () => void {
    const buffered: RunEvent[] = [];
    let replaying = true;
    const listener = (event: RunEvent) => {
      if (replaying) {
        buffered.push(event);
      } else {
        onEvent(event);
      }
    };
    this.bus.on(runId, listener);

    const lines = this.readLog(runId);
    lines.forEach((line, index) => onEvent({ seq: index + 1, type: "log", data: line }));
    const last = lines.length;
    const run = this.getRun(runId);
    if (run) {
      onEvent({ seq: last, type: "status", data: run.status });
    }
    for (const event of buffered) {
      if (event.type === "status" || event.seq > last) {
        onEvent(event);
      }
    }
    replaying = false;
    return () => this.bus.off(runId, listener);
  }

  private logPath(runId: string): string {
    return path.join(this.config.dataDir, "jobs", `${runId}.log`);
  }

  private readLog(runId: string): string[] {
    try {
      const text = fs.readFileSync(this.logPath(runId), "utf-8");
      return text === "" ? [] : text.replace(/\r?\n$/, "").split(/\r?\n/);
    } catch {
      return [];
    }
  }

  private emit(runId: string, type: RunEvent["type"], data: string): void {
    const seq = type === "log" ? (this.counters.get(runId) ?? 0) + 1 : (this.counters.get(runId) ?? 0);
    if (type === "log") {
      this.counters.set(runId, seq);
    }
    this.bus.emit(runId, { seq, type, data } satisfies RunEvent);
  }

  private async pump(): Promise<void> {
    if (this.pumping) {
      return;
    }
    this.pumping = true;
    try {
      for (;;) {
        const job = this.db
          .prepare("SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at, rowid LIMIT 1")
          .get() as { id: string; run_id: string; args_json: string; log_path: string } | undefined;
        if (!job) {
          return;
        }
        await this.execute(job);
      }
    } finally {
      this.pumping = false;
    }
  }

  private execute(job: { id: string; run_id: string; args_json: string; log_path: string }): Promise<void> {
    const request = JSON.parse(job.args_json) as RunRequest;
    const run = this.getRun(job.run_id);
    if (!run) {
      return Promise.resolve();
    }
    const started = new Date().toISOString();
    this.db.prepare("UPDATE jobs SET status = 'running', started_at = ? WHERE id = ?").run(started, job.id);
    this.db.prepare("UPDATE runs SET status = 'running', started_at = ? WHERE id = ?").run(started, run.id);
    this.emit(run.id, "status", "running");
    this.counters.set(run.id, this.readLog(run.id).length);

    const spec = this.build(request, run.run_dir);
    const tail: string[] = [];
    const record = (line: string) => {
      fs.appendFileSync(job.log_path, `${line}\n`);
      tail.push(line);
      if (tail.length > 8) {
        tail.shift();
      }
      this.emit(run.id, "log", line);
    };

    return new Promise<void>((resolve) => {
      let settled = false;
      const finish = (code: number | null, failure?: string) => {
        if (settled) {
          return;
        }
        settled = true;
        this.current = null;
        this.finalise(job.id, run.id, run.run_dir, code, failure ?? tail.slice(-4).join("\n"));
        resolve();
      };
      let child: ChildProcess;
      try {
        child = spawn(spec.bin, spec.args, {
          cwd: spec.cwd,
          shell: false,
          windowsHide: true,
          env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
        });
      } catch (error) {
        finish(null, `Could not start ${spec.bin}: ${(error as Error).message}`);
        return;
      }
      this.current = child;
      for (const stream of [child.stdout, child.stderr]) {
        let pending = "";
        stream?.setEncoding("utf-8");
        stream?.on("data", (chunk: string) => {
          pending += chunk;
          const parts = pending.split(/\r?\n/);
          pending = parts.pop() ?? "";
          parts.filter((line) => line.trim() !== "").forEach(record);
        });
        stream?.on("end", () => {
          if (pending.trim() !== "") {
            record(pending);
          }
        });
      }
      child.on("error", (error) => finish(null, `Could not start ${spec.bin}: ${error.message}`));
      child.on("close", (code) => finish(code));
    });
  }

  private finalise(jobId: string, runId: string, runDir: string, code: number | null, detail: string): void {
    const finished = new Date().toISOString();
    let status: RunRow["status"] = "failed";
    let manifest: Record<string, unknown> | null = null;
    if (code === 0) {
      try {
        manifest = JSON.parse(fs.readFileSync(path.join(runDir, "manifest.json"), "utf-8"));
        status = manifest?.status === "empty" ? "empty" : "ok";
      } catch {
        detail = "The pipeline finished but wrote no manifest.json.";
      }
    }
    this.db
      .prepare(
        `UPDATE runs SET status = ?, git_commit = ?, config_hash = ?, counts_json = ?, error = ?, finished_at = ?
         WHERE id = ?`,
      )
      .run(
        status,
        (manifest?.git_commit as string | undefined) ?? null,
        (manifest?.config_hash as string | undefined) ?? null,
        manifest?.counts ? JSON.stringify(manifest.counts) : null,
        status === "failed" ? detail || `Exited with code ${code}` : null,
        finished,
        runId,
      );
    this.db
      .prepare("UPDATE jobs SET status = ?, exit_code = ?, finished_at = ? WHERE id = ?")
      .run(status === "failed" ? "failed" : "succeeded", code, finished, jobId);
    this.emit(runId, "status", status);
  }
}

export const isFinished = (status: string): boolean => FINISHED.has(status);
