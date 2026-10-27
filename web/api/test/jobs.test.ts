import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { JobQueue, pythonCommand } from "../src/jobs.js";
import { harness, stubPipeline, WRITE_MANIFEST } from "./helpers.js";

const REQUEST = { sector: "Capital Goods", period: "2026Q3", offline: true } as const;

describe("JobQueue", () => {
  it("runs the pipeline and records the manifest", async () => {
    const { queue } = harness(stubPipeline(WRITE_MANIFEST("ok")));
    const { runId } = queue.enqueue({ ...REQUEST });
    await queue.idle();
    const run = queue.getRun(runId)!;
    expect(run.status).toBe("ok");
    expect(run.git_commit).toBe("abc123");
    expect(run.config_hash).toBe("hash42");
    expect(JSON.parse(run.counts_json!)).toEqual({ screening: 3, review: 5 });
    expect(run.error).toBeNull();
    expect(run.started_at).not.toBeNull();
    expect(run.finished_at).not.toBeNull();
  });

  it("keeps an empty run distinct from a failed one", async () => {
    const { queue } = harness(stubPipeline(WRITE_MANIFEST("empty")));
    const { runId } = queue.enqueue({ ...REQUEST });
    await queue.idle();
    expect(queue.getRun(runId)!.status).toBe("empty");
  });

  it("fails with the last output lines when the process exits non-zero", async () => {
    const { queue } = harness(
      stubPipeline("console.error('Could not reach the Colombo Stock Exchange'); process.exit(1)"),
    );
    const { runId } = queue.enqueue({ ...REQUEST });
    await queue.idle();
    const run = queue.getRun(runId)!;
    expect(run.status).toBe("failed");
    expect(run.error).toContain("Could not reach the Colombo Stock Exchange");
  });

  it("fails when the pipeline succeeds without writing a manifest", async () => {
    const { queue } = harness(stubPipeline("console.log('done')"));
    const { runId } = queue.enqueue({ ...REQUEST });
    await queue.idle();
    const run = queue.getRun(runId)!;
    expect(run.status).toBe("failed");
    expect(run.error).toMatch(/manifest/);
  });

  it("fails cleanly when the interpreter cannot be started", async () => {
    const { queue } = harness(() => ({ bin: "definitely-not-a-real-binary", args: [], cwd: "." }));
    const { runId } = queue.enqueue({ ...REQUEST });
    await queue.idle();
    const run = queue.getRun(runId)!;
    expect(run.status).toBe("failed");
    expect(run.error).toMatch(/Could not start/);
  });

  it("processes runs one at a time, in order", async () => {
    const script = `${WRITE_MANIFEST("ok")}
      const t = Date.now(); while (Date.now() - t < 120) {}`;
    const { queue } = harness(stubPipeline(script));
    const first = queue.enqueue({ ...REQUEST, period: "2026Q1" });
    const second = queue.enqueue({ ...REQUEST, period: "2026Q2" });
    expect(queue.getRun(second.runId)!.status).toBe("queued");
    await queue.idle();
    const a = queue.getRun(first.runId)!;
    const b = queue.getRun(second.runId)!;
    expect([a.status, b.status]).toEqual(["ok", "ok"]);
    expect(a.finished_at! <= b.started_at!).toBe(true);
  });

  it("marks runs left over from a previous server session as failed", async () => {
    const { db, config } = harness(stubPipeline(WRITE_MANIFEST("ok")));
    db.prepare(
      `INSERT INTO runs (id, sector, period, status, run_dir, created_at)
       VALUES ('old-run', 'Banks', '2026Q3', 'running', 'x', '2026-01-01T00:00:00Z')`,
    ).run();
    const restarted = new JobQueue(config, db, stubPipeline(WRITE_MANIFEST("ok")));
    expect(restarted.getRun("old-run")!.status).toBe("failed");
    expect(restarted.getRun("old-run")!.error).toMatch(/stopped/);
  });

  it("writes a replayable log file", async () => {
    const { queue, config } = harness(stubPipeline(WRITE_MANIFEST("ok")));
    const { runId } = queue.enqueue({ ...REQUEST });
    await queue.idle();
    const log = fs.readFileSync(path.join(config.dataDir, "jobs", `${runId}.log`), "utf-8");
    expect(log).toContain("stub run started");
  });
});

describe("pythonCommand", () => {
  it("builds an argument array with no shell string", () => {
    const { config } = harness();
    const spec = pythonCommand(config)(
      { sector: "Banks", period: "2026Q3", ticker: "COMB.N0000", offline: true },
      "/runs/r1",
    );
    expect(spec.bin).toBe(config.pythonBin);
    expect(spec.cwd).toBe(config.repoRoot);
    expect(spec.args).toEqual([
      "main.py",
      "run",
      "--sector",
      "Banks",
      "--period",
      "2026Q3",
      "--company",
      "COMB.N0000",
      "--offline",
      "--run-dir",
      "/runs/r1",
    ]);
  });

  it("omits the optional flags", () => {
    const { config } = harness();
    const spec = pythonCommand(config)({ sector: "Banks", period: "2026", offline: false }, "/r");
    expect(spec.args).not.toContain("--company");
    expect(spec.args).not.toContain("--offline");
  });
});
