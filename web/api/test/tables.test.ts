import fs from "node:fs";
import path from "node:path";
import request from "supertest";
import { describe, expect, it } from "vitest";
import { harness, seedRun } from "./helpers.js";

const SCREENING = [
  { Ticker: "AAA.N0000", Company: "AAA PLC", Revenue: "100", "Data Confidence": "high" },
  { Ticker: "BBB.N0000", Company: "BBB PLC", Revenue: null, "Data Confidence": "low" },
];

describe("run tables", () => {
  it("serves the pipeline's rows untouched, optionally for one ticker", async () => {
    const h = harness();
    seedRun(h, "run-1", {
      screening: SCREENING,
      raw_facts: [{ "Fact ID": "AAA.N0000:1:revenue:5", Ticker: "AAA.N0000" }],
      summary: [{ Metric: "Sector median ROE", Value: 0.12, Observations: 5 }],
    });
    const all = await request(h.app).get("/api/runs/run-1/screening");
    expect(all.body).toEqual(SCREENING);
    const one = await request(h.app).get("/api/runs/run-1/screening?ticker=BBB.N0000");
    expect(one.body).toEqual([SCREENING[1]]);
    const facts = await request(h.app).get("/api/runs/run-1/facts");
    expect(facts.body[0]["Fact ID"]).toBe("AAA.N0000:1:revenue:5");
    const summary = await request(h.app).get("/api/runs/run-1/summary");
    expect(summary.body[0].Metric).toBe("Sector median ROE");
  });

  it("refuses tables that are not listed and bad filters", async () => {
    const h = harness();
    seedRun(h, "run-1", { screening: SCREENING });
    expect((await request(h.app).get("/api/runs/run-1/manifest")).status).toBe(404);
    expect((await request(h.app).get("/api/runs/run-1/__proto__")).status).toBe(404);
    expect((await request(h.app).get("/api/runs/run-1/screening?ticker=x;y")).status).toBe(400);
    expect((await request(h.app).get("/api/runs/missing/screening")).status).toBe(404);
    expect((await request(h.app).get("/api/runs/..%2Fx/screening")).status).toBe(404);
  });

  it("says so when a run has no table yet", async () => {
    const h = harness();
    seedRun(h, "run-1", {});
    const res = await request(h.app).get("/api/runs/run-1/ratios");
    expect(res.status).toBe(409);
    expect(res.body.error).toBe("not_ready");
  });
});

describe("cited documents", () => {
  function setup() {
    const h = harness();
    const cache = path.join(h.config.repoRoot, "data", "raw", "AAA_N0000");
    fs.mkdirSync(cache, { recursive: true });
    const pdf = path.join(cache, "f1.pdf");
    fs.writeFileSync(pdf, "%PDF-1.4 stub");
    const secret = path.join(h.root, "secret.pdf");
    fs.writeFileSync(secret, "%PDF-1.4 secret");
    seedRun(h, "run-1", {
      sources: [
        { Ticker: "AAA.N0000", "Document ID": "aaaaaaaaaaaaaaaa", "Local Path": pdf },
        { Ticker: "AAA.N0000", "Document ID": "bbbbbbbbbbbbbbbb", "Local Path": secret },
        { Ticker: "AAA.N0000", "Document ID": "cccccccccccccccc", "Local Path": path.join(cache, "gone.pdf") },
      ],
    });
    return h;
  }

  it("streams a cached PDF inline", async () => {
    const h = setup();
    const res = await request(h.app).get("/api/documents/AAA.N0000/aaaaaaaaaaaaaaaa/file");
    expect(res.status).toBe(200);
    expect(res.headers["content-type"]).toBe("application/pdf");
    expect(res.headers["content-disposition"]).toBe("inline");
    expect(res.headers["x-content-type-options"]).toBe("nosniff");
    expect(res.body.toString()).toContain("%PDF-1.4 stub");
  });

  it("never serves a recorded path outside the pipeline's cache", async () => {
    const h = setup();
    expect((await request(h.app).get("/api/documents/AAA.N0000/bbbbbbbbbbbbbbbb/file")).status).toBe(404);
  });

  it("404s for missing files, wrong tickers and malformed ids", async () => {
    const h = setup();
    expect((await request(h.app).get("/api/documents/AAA.N0000/cccccccccccccccc/file")).status).toBe(404);
    expect((await request(h.app).get("/api/documents/ZZZ.N0000/aaaaaaaaaaaaaaaa/file")).status).toBe(404);
    expect((await request(h.app).get("/api/documents/AAA.N0000/..%2F..%2Fx/file")).status).toBe(400);
    expect((await request(h.app).get("/api/documents/not-a-ticker/aaaaaaaaaaaaaaaa/file")).status).toBe(400);
  });
});
