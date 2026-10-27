import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { GROUP_NAMES, groupSlug } from "../src/universe.js";
import { parseRunRequest, ValidationError } from "../src/validation.js";

const here = path.dirname(fileURLToPath(import.meta.url));

describe("parseRunRequest", () => {
  it("accepts a sector, a period and an optional ticker", () => {
    expect(parseRunRequest({ sector: "Banks", period: "2026q3", ticker: "COMB.X0000", offline: true })).toEqual({
      sector: "Banks",
      period: "2026Q3",
      ticker: "COMB.X0000",
      offline: true,
    });
    expect(parseRunRequest({ sector: "Capital Goods", period: "2026" })).toEqual({
      sector: "Capital Goods",
      period: "2026",
      ticker: undefined,
      offline: false,
    });
  });

  it.each([
    [{ sector: "Banks; rm -rf /", period: "2026Q3" }],
    [{ sector: "banks", period: "2026Q3" }],
    [{ sector: "Banks", period: "2026Q5" }],
    [{ sector: "Banks", period: "next quarter" }],
    [{ sector: "Banks", period: "2026Q3", ticker: "ACL.N0000; calc" }],
    [{ sector: "Banks", period: "2026Q3", ticker: "acl.n0000" }],
    [{ sector: "Banks", period: "2026Q3", ticker: "../../etc/passwd" }],
    [{ sector: "Banks", period: "2026Q3", offline: "yes" }],
    [null],
    ["Banks"],
  ])("rejects %j", (body) => {
    expect(() => parseRunRequest(body)).toThrow(ValidationError);
  });
});

describe("industry groups", () => {
  it("match SUPPORTED_INDUSTRY_GROUPS in the Python package", () => {
    const source = fs.readFileSync(
      path.resolve(here, "..", "..", "..", "src", "cse_screening", "downloaders", "universe.py"),
      "utf-8",
    );
    const block = /SUPPORTED_INDUSTRY_GROUPS = \(([\s\S]*?)\n\)/.exec(source)?.[1] ?? "";
    const python = [...block.matchAll(/"([^"]+)"/g)].map((match) => match[1]);
    expect(GROUP_NAMES).toEqual(python);
  });

  it("slugs match the file names the Python cache writes", () => {
    expect(groupSlug("Technology Hardware & Equipment")).toBe("technology_hardware_equipment");
    expect(groupSlug("Food, Beverage & Tobacco")).toBe("food_beverage_tobacco");
  });
});
