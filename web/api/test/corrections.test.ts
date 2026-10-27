import request from "supertest";
import { describe, expect, it } from "vitest";
import type { PythonRunner } from "../src/python.js";
import { correctionArgs, parseCorrection } from "../src/routes/corrections.js";
import { harness } from "./helpers.js";

const BODY = {
  ticker: "ACL.N0000",
  metric: "net_profit",
  value: "1,250.5",
  unit: "LKR million",
  periodEnd: "2026-03-31",
  document: "Annual Report as at 31st March 2026",
  sourcePage: 122,
  scope: "group",
  reason: "OCR read 7 as 1",
};

function setup(python?: PythonRunner) {
  const calls: string[][] = [];
  let counter = 0;
  const runner: PythonRunner =
    python ??
    (async () => ({ code: 0, stdout: `correction: ACL.N0000-net_profit-2026-03-31-${++counter}\n`, stderr: "" }));
  return { ...harness(undefined, {}, { python: async (args) => (calls.push(args), runner(args)) }), calls };
}

describe("parseCorrection", () => {
  it("normalises a valid correction", () => {
    expect(parseCorrection(BODY)).toMatchObject({ value: "1250.5", author: "reviewer", scope: "group" });
  });

  it.each([
    [{ ticker: "ACL.N0000 --evil" }],
    [{ metric: "Net Profit" }],
    [{ value: "12abc" }],
    [{ value: "1e9" }],
    [{ unit: "dollars" }],
    [{ periodEnd: "March 2026" }],
    [{ sourcePage: 0 }],
    [{ sourcePage: "12; rm" }],
    [{ scope: "everything" }],
    [{ reason: "no" }],
    [{ supersedes: "../x" }],
  ])("rejects %j", (over) => {
    expect(() => parseCorrection({ ...BODY, ...over })).toThrow();
  });

  it("builds --flag=value arguments, so a leading dash cannot become an option", () => {
    const args = correctionArgs(parseCorrection({ ...BODY, document: "-Annual report", reason: "--supersedes=x because" }));
    expect(args).toContain("--document=-Annual report");
    expect(args).toContain("--reason=--supersedes=x because");
    expect(args.filter((arg) => arg.startsWith("--supersedes"))).toEqual([]);
    expect(args.slice(0, 2)).toEqual(["corrections", "add"]);
  });
});

describe("corrections API", () => {
  it("adds a correction through Python and logs it", async () => {
    const h = setup();
    const res = await request(h.app).post("/api/corrections").send(BODY);
    expect(res.status).toBe(201);
    expect(res.body.correctionId).toBe("ACL.N0000-net_profit-2026-03-31-1");
    expect(h.calls[0]).toContain("--value=1250.5");
    expect(h.calls[0]).toContain("--source-page=122");
    const list = await request(h.app).get("/api/corrections?ticker=ACL.N0000&metric=net_profit");
    expect(list.body).toHaveLength(1);
    expect(list.body[0]).toMatchObject({ correctionId: "ACL.N0000-net_profit-2026-03-31-1", superseded: false, reason: "OCR read 7 as 1" });
  });

  it("marks the older correction superseded, never deleting it", async () => {
    const h = setup();
    await request(h.app).post("/api/corrections").send(BODY);
    await request(h.app).post("/api/corrections").send({ ...BODY, value: "1300", supersedes: "ACL.N0000-net_profit-2026-03-31-1" });
    expect(h.calls[1]).toContain("--supersedes=ACL.N0000-net_profit-2026-03-31-1");
    const list = (await request(h.app).get("/api/corrections")).body as { correctionId: string; superseded: boolean }[];
    expect(list.map((item) => [item.correctionId, item.superseded])).toEqual([
      ["ACL.N0000-net_profit-2026-03-31-2", false],
      ["ACL.N0000-net_profit-2026-03-31-1", true],
    ]);
  });

  it("reports the pipeline's refusal and logs nothing", async () => {
    const h = setup(async () => ({ code: 2, stdout: "", stderr: "main.py: error: No correction with id 'x' to supersede" }));
    const res = await request(h.app).post("/api/corrections").send({ ...BODY, supersedes: "x" });
    expect(res.status).toBe(422);
    expect(res.body.message).toContain("to supersede");
    expect((await request(h.app).get("/api/corrections")).body).toEqual([]);
  });

  it("rejects invalid input before Python runs", async () => {
    const h = setup();
    const res = await request(h.app).post("/api/corrections").send({ ...BODY, ticker: "x" });
    expect(res.status).toBe(400);
    expect(h.calls).toHaveLength(0);
  });
});
