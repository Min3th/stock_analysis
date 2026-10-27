import request from "supertest";
import { describe, expect, it } from "vitest";
import type { PdfRenderer } from "../src/pdf.js";
import { exportTarget } from "../src/routes/exports.js";
import { harness, seedRun } from "./helpers.js";

function setup(fail = false) {
  const calls: { path: string; landscape: boolean }[] = [];
  const pdf: PdfRenderer = {
    async render(path, options) {
      calls.push({ path, landscape: options.landscape });
      if (fail) throw new Error("Browser crashed\n    at stack");
      return Buffer.from("%PDF-1.4 rendered");
    },
    async close() {},
  };
  const h = harness(undefined, {}, { pdf });
  seedRun(h, "run-1", { screening: [] });
  return { ...h, calls };
}

describe("exportTarget", () => {
  it("maps each export to its print route, orientation and file name", () => {
    expect(exportTarget("sector", "run-1")).toEqual({ path: "/print/sector/run-1", landscape: true, filename: "Sector_report_run-1.pdf" });
    expect(exportTarget("review", "run-1")).toMatchObject({ path: "/print/review/run-1", landscape: false });
    expect(exportTarget("company", "run-1", "ACL.N0000")).toEqual({
      path: "/print/company/run-1/ACL.N0000",
      landscape: false,
      filename: "ACL.N0000_run-1.pdf",
    });
  });
});

describe("POST /api/exports", () => {
  it.each([
    [{ type: "sector" }, "/print/sector/run-1", true],
    [{ type: "review" }, "/print/review/run-1", false],
    [{ type: "company", ticker: "ACL.N0000" }, "/print/company/run-1/ACL.N0000", false],
  ])("renders %j", async (body, path, landscape) => {
    const h = setup();
    const res = await request(h.app).post("/api/exports").send({ runId: "run-1", ...body });
    expect(res.status).toBe(200);
    expect(res.headers["content-type"]).toBe("application/pdf");
    expect(res.headers["content-disposition"]).toMatch(/^attachment; filename="[\w.-]+\.pdf"$/);
    expect(res.body.toString()).toContain("%PDF-1.4");
    expect(h.calls).toEqual([{ path, landscape }]);
  });

  it("validates input before rendering", async () => {
    const h = setup();
    for (const body of [
      { type: "pdf", runId: "run-1" },
      { type: "sector", runId: "../x" },
      { type: "company", runId: "run-1" },
      { type: "company", runId: "run-1", ticker: "ACL.N0000/../../admin" },
    ]) {
      expect((await request(h.app).post("/api/exports").send(body)).status).toBe(400);
    }
    expect((await request(h.app).post("/api/exports").send({ type: "sector", runId: "missing" })).status).toBe(404);
    expect(h.calls).toHaveLength(0);
  });

  it("refuses to export a run that has not completed", async () => {
    const h = setup();
    h.db.prepare("UPDATE runs SET status = 'running' WHERE id = 'run-1'").run();
    const res = await request(h.app).post("/api/exports").send({ type: "sector", runId: "run-1" });
    expect(res.status).toBe(409);
    expect(h.calls).toHaveLength(0);
  });

  it("reports a rendering failure without a stack trace", async () => {
    const h = setup(true);
    const res = await request(h.app).post("/api/exports").send({ type: "sector", runId: "run-1" });
    expect(res.status).toBe(502);
    expect(res.body.message).toBe("The PDF could not be rendered: Browser crashed");
  });
});
