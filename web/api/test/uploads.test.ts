import fs from "node:fs";
import path from "node:path";
import request from "supertest";
import { describe, expect, it } from "vitest";
import type { PythonRunner } from "../src/python.js";
import { harness } from "./helpers.js";

const PREVIEW = {
  file: "x.pdf",
  pages: 3,
  facts: [{ metric: "revenue", value: "100", page: 2, confidence: "0.9", below_threshold: false }],
};
const PDF = Buffer.from("%PDF-1.4 stub");

function setup(python?: PythonRunner) {
  const calls: string[][] = [];
  const inner: PythonRunner =
    python ??
    (async (args) =>
      args[0] === "extract"
        ? { code: 0, stdout: JSON.stringify(PREVIEW), stderr: "" }
        : { code: 0, stdout: "upload: abc config", stderr: "" });
  const recording: PythonRunner = async (args) => {
    calls.push(args);
    return inner(args);
  };
  return { ...harness(undefined, {}, { python: recording }), calls };
}

function withFields(req: request.Test, over: Record<string, string | undefined> = {}) {
  const fields = { ticker: "ACL.N0000", kind: "annual_report", periodEnd: "2026-03-31", ...over };
  for (const [key, value] of Object.entries(fields)) if (value !== undefined) req.field(key, value);
  return req;
}

const pendingDir = (h: ReturnType<typeof setup>) => path.join(h.config.dataDir, "uploads", "pending");

describe("uploads", () => {
  it("previews an upload, then accepts it through the pipeline", async () => {
    const h = setup();
    const created = await withFields(request(h.app).post("/api/uploads")).attach("file", PDF, "../../evil name.pdf");
    expect(created.status).toBe(201);
    expect(created.body.status).toBe("pending");
    expect(created.body.originalFilename).toBe("evil name.pdf");
    expect(created.body.preview.facts[0].metric).toBe("revenue");
    const stored = path.join(pendingDir(h), `${created.body.sha256.slice(0, 16)}.pdf`);
    expect(fs.existsSync(stored)).toBe(true);
    expect(h.calls[0]).toEqual(["extract", "--pdf", stored, "--kind", "annual_report", "--period-end", "2026-03-31"]);

    const accepted = await request(h.app)
      .post(`/api/uploads/${created.body.id}/accept`)
      .send({ title: "ACL AR 2026" });
    expect(accepted.status).toBe(200);
    expect(accepted.body.status).toBe("accepted");
    expect(h.calls[1]).toEqual([
      "uploads", "add", "--pdf", stored, "--ticker", "ACL.N0000", "--kind", "annual_report",
      "--period-end", "2026-03-31", "--title=ACL AR 2026", "--original-name=evil name.pdf",
    ]);
    expect(fs.existsSync(stored)).toBe(false);
    expect((await request(h.app).post(`/api/uploads/${created.body.id}/accept`).send({})).status).toBe(409);
  });

  it("reads the preview even when a library prints a notice first", async () => {
    const h = setup(async () => ({
      code: 0,
      stdout: `Consider using the pymupdf_layout package.
${JSON.stringify(PREVIEW, null, 1)}
`,
      stderr: "",
    }));
    const res = await withFields(request(h.app).post("/api/uploads")).attach("file", PDF, "a.pdf");
    expect(res.status).toBe(201);
    expect(res.body.preview.pages).toBe(3);
  });

  it("passes the interim length to Python", async () => {
    const h = setup();
    const res = await withFields(request(h.app).post("/api/uploads"), {
      kind: "interim_statement",
      periodEnd: "2026-06-30",
      periodMonths: "3",
    }).attach("file", PDF, "q1.pdf");
    expect(res.status).toBe(201);
    expect(h.calls[0]).toContain("--period-months");
  });

  it("rejects non-PDFs, bad fields and oversized files before extraction", async () => {
    const h = setup();
    const notPdf = await withFields(request(h.app).post("/api/uploads")).attach("file", Buffer.from("<html>"), "a.pdf");
    expect(notPdf.status).toBe(400);
    expect(notPdf.body.error).toBe("not_a_pdf");
    for (const over of [
      { ticker: "ACL.N0000; x" },
      { kind: "other" },
      { periodEnd: "31/03/2026" },
      { kind: "interim_statement" },
    ]) {
      const res = await withFields(request(h.app).post("/api/uploads"), over).attach("file", PDF, "a.pdf");
      expect(res.status).toBe(400);
    }
    expect((await withFields(request(h.app).post("/api/uploads"))).status).toBe(400);
    expect(h.calls).toHaveLength(0);
    expect(fs.readdirSync(pendingDir(h))).toEqual([]);

    const tiny = setup();
    const small = harness(undefined, { UPLOAD_LIMIT_MB: "1" });
    const big = await withFields(request(small.app).post("/api/uploads")).attach("file", Buffer.alloc(1.5 * 1024 * 1024, 1), "big.pdf");
    expect(big.status).toBe(413);
    expect(tiny.calls).toHaveLength(0);
  });

  it("surfaces an extractor failure and keeps nothing", async () => {
    const h = setup(async () => ({ code: 1, stdout: "", stderr: "Could not read the PDF: broken" }));
    const res = await withFields(request(h.app).post("/api/uploads")).attach("file", PDF, "a.pdf");
    expect(res.status).toBe(422);
    expect(res.body.message).toContain("broken");
    expect((await request(h.app).get("/api/uploads")).body).toEqual([]);
    expect(fs.readdirSync(pendingDir(h))).toEqual([]);
  });

  it("reports the pipeline's refusal when accepting, and can discard", async () => {
    const h = setup(async (args) =>
      args[0] === "extract"
        ? { code: 0, stdout: JSON.stringify(PREVIEW), stderr: "" }
        : { code: 2, stdout: "", stderr: "main.py: error: ZZZ.N0000 is not in the known CSE universe; upload rejected" },
    );
    const created = await withFields(request(h.app).post("/api/uploads"), { ticker: "ZZZ.N0000" }).attach("file", PDF, "a.pdf");
    const refused = await request(h.app).post(`/api/uploads/${created.body.id}/accept`).send({});
    expect(refused.status).toBe(422);
    expect(refused.body.message).toContain("known CSE universe");
    expect((await request(h.app).get(`/api/uploads/${created.body.id}`)).body.status).toBe("pending");
    const discarded = await request(h.app).delete(`/api/uploads/${created.body.id}`);
    expect(discarded.body.status).toBe("rejected");
    expect((await request(h.app).delete(`/api/uploads/${created.body.id}`)).status).toBe(409);
    expect((await request(h.app).get("/api/uploads/..%2Fx")).status).toBe(404);
  });
});
