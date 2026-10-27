import fs from "node:fs";
import http from "node:http";
import type { AddressInfo } from "node:net";
import path from "node:path";
import request from "supertest";
import { describe, expect, it } from "vitest";
import { harness, stubPipeline, WRITE_MANIFEST } from "./helpers.js";

describe("runs API", () => {
  it("rejects invalid requests before anything is started", async () => {
    const { app, queue } = harness(stubPipeline(WRITE_MANIFEST("ok")));
    for (const body of [
      { sector: "Banks; calc", period: "2026Q3" },
      { sector: "Banks", period: "2026Q3", ticker: "ACL.N0000 && dir" },
      {},
    ]) {
      const res = await request(app).post("/api/runs").send(body);
      expect(res.status).toBe(400);
      expect(res.body.error).toBe("invalid_request");
    }
    expect(queue.listRuns()).toHaveLength(0);
    const malformed = await request(app)
      .post("/api/runs")
      .set("Content-Type", "application/json")
      .send("{not json");
    expect(malformed.status).toBe(400);
  });

  it("starts a run, lists it and reports its outcome", async () => {
    const { app, queue } = harness(stubPipeline(WRITE_MANIFEST("ok")));
    const created = await request(app)
      .post("/api/runs")
      .send({ sector: "Capital Goods", period: "2026q3", offline: true });
    expect(created.status).toBe(202);
    const { runId } = created.body as { runId: string };
    expect(runId).toMatch(/^\d{14}-capital_goods-2026Q3-[0-9a-f]{4}$/);
    await queue.idle();

    const one = await request(app).get(`/api/runs/${runId}`);
    expect(one.body).toMatchObject({
      id: runId,
      sector: "Capital Goods",
      period: "2026Q3",
      offline: true,
      status: "ok",
      gitCommit: "abc123",
      counts: { screening: 3, review: 5 },
    });
    expect(one.body).not.toHaveProperty("run_dir");
    const list = await request(app).get("/api/runs");
    expect(list.body.map((run: { id: string }) => run.id)).toEqual([runId]);
  });

  it("answers 404 for unknown or malformed ids", async () => {
    const { app } = harness();
    expect((await request(app).get("/api/runs/nope")).status).toBe(404);
    expect((await request(app).get("/api/runs/..%2F..%2Fsecret")).status).toBe(404);
    expect((await request(app).get("/api/runs/nope/events")).status).toBe(404);
  });
});

describe("universe API", () => {
  it("lists every group with its cache state", async () => {
    const { app, config } = harness();
    const cache = path.join(config.repoRoot, "data", "raw", "cse_universe");
    fs.mkdirSync(cache, { recursive: true });
    fs.writeFileSync(
      path.join(cache, "banks.json"),
      JSON.stringify({
        group: { industry_group: "Banks" },
        companies: [{ ticker: "COMB.N0000", name: "COMMERCIAL BANK OF CEYLON PLC" }],
      }),
    );
    const groups = (await request(app).get("/api/universe/groups")).body as {
      name: string;
      cached: boolean;
    }[];
    expect(groups).toHaveLength(22);
    expect(groups.find((group) => group.name === "Banks")!.cached).toBe(true);
    expect(groups.find((group) => group.name === "Energy")!.cached).toBe(false);

    const banks = await request(app).get("/api/universe/Banks");
    expect(banks.body.companies).toEqual([
      { ticker: "COMB.N0000", name: "COMMERCIAL BANK OF CEYLON PLC", industryGroup: "Banks" },
    ]);
    expect((await request(app).get("/api/universe/Energy")).status).toBe(404);
    expect((await request(app).get("/api/universe/..%2F..")).status).toBe(404);
  });
});

function readEvents(port: number, runId: string): Promise<{ event: string; data: string }[]> {
  return new Promise((resolve, reject) => {
    const events: { event: string; data: string }[] = [];
    http
      .get({ host: "127.0.0.1", port, path: `/api/runs/${runId}/events` }, (res) => {
        expect(res.headers["content-type"]).toContain("text/event-stream");
        let buffer = "";
        res.setEncoding("utf-8");
        res.on("data", (chunk: string) => {
          buffer += chunk;
          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";
          for (const frame of frames) {
            const event = /^event: (.*)$/m.exec(frame)?.[1];
            const data = /^data: (.*)$/m.exec(frame)?.[1];
            if (event && data !== undefined) {
              events.push({ event, data: JSON.parse(data) });
            }
          }
        });
        res.on("end", () => resolve(events));
        res.on("error", reject);
      })
      .on("error", reject);
  });
}

describe("run events (SSE)", () => {
  it("streams live output then ends, and replays the log afterwards", async () => {
    const script = `${WRITE_MANIFEST("ok")}
      const t = Date.now(); while (Date.now() - t < 100) {}`;
    const { app, queue } = harness(stubPipeline(script));
    const server = app.listen(0, "127.0.0.1");
    await new Promise((resolve) => server.once("listening", resolve));
    try {
      const port = (server.address() as AddressInfo).port;
      const { runId } = queue.enqueue({ sector: "Capital Goods", period: "2026Q3", offline: true });
      const live = await readEvents(port, runId);
      const lines = live.filter((e) => e.event === "log").map((e) => e.data);
      expect(lines[0]).toBe("stub run started");
      expect(lines[1]).toMatch(/^xlsx: /);
      expect(live.at(-1)).toEqual({ event: "end", data: "ok" });
      expect(live.filter((e) => e.event === "log")).toHaveLength(2);

      await queue.idle();
      const replay = await readEvents(port, runId);
      expect(replay.filter((e) => e.event === "log").map((e) => e.data)).toEqual(lines);
      expect(replay.at(-1)).toEqual({ event: "end", data: "ok" });
    } finally {
      server.close();
    }
  });
});
