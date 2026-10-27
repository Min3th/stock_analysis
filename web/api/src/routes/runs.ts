import { Router } from "express";
import { isFinished, type JobQueue, type RunRow } from "../jobs.js";
import { ID_PATTERN, parseRunRequest, ValidationError } from "../validation.js";

/** Shape returned to the UI; paths on disk stay on the server. */
export function presentRun(row: RunRow) {
  return {
    id: row.id,
    sector: row.sector,
    period: row.period,
    ticker: row.ticker,
    offline: row.offline === 1,
    status: row.status,
    gitCommit: row.git_commit,
    configHash: row.config_hash,
    counts: row.counts_json ? (JSON.parse(row.counts_json) as Record<string, number>) : null,
    error: row.error,
    createdAt: row.created_at,
    startedAt: row.started_at,
    finishedAt: row.finished_at,
  };
}

export function runsRouter(queue: JobQueue): Router {
  const router = Router();

  router.post("/runs", (req, res) => {
    try {
      const request = parseRunRequest(req.body);
      const { runId, jobId } = queue.enqueue(request);
      res.status(202).json({ runId, jobId });
    } catch (error) {
      if (error instanceof ValidationError) {
        res.status(400).json({ error: "invalid_request", message: error.message });
        return;
      }
      throw error;
    }
  });

  router.get("/runs", (_req, res) => {
    res.json(queue.listRuns().map(presentRun));
  });

  router.get("/runs/:id", (req, res) => {
    const run = ID_PATTERN.test(req.params.id) ? queue.getRun(req.params.id) : undefined;
    if (!run) {
      res.status(404).json({ error: "not_found" });
      return;
    }
    res.json(presentRun(run));
  });

  // Server-sent events: the stored log is replayed, then new lines stream live.
  router.get("/runs/:id/events", (req, res) => {
    const id = req.params.id;
    const run = ID_PATTERN.test(id) ? queue.getRun(id) : undefined;
    if (!run) {
      res.status(404).json({ error: "not_found" });
      return;
    }
    res.writeHead(200, {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    });
    const send = (event: string, data: string) => {
      res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
    };
    let closed = false;
    const close = () => {
      if (closed) {
        return;
      }
      closed = true;
      clearInterval(heartbeat);
      unsubscribe();
      res.end();
    };
    const heartbeat = setInterval(() => res.write(": keep-alive\n\n"), 15_000);
    const unsubscribe = queue.subscribe(id, (event) => {
      if (closed) {
        return;
      }
      send(event.type, event.data);
      if (event.type === "status" && isFinished(event.data)) {
        send("end", event.data);
        // Defer so the subscribe() call that is replaying has returned.
        setImmediate(close);
      }
    });
    req.on("close", close);
  });

  return router;
}
