import request from "supertest";
import { describe, expect, it } from "vitest";
import { loadConfig } from "../src/config.js";
import { harness } from "./helpers.js";

describe("health", () => {
  it("reports the loopback binding and the schema", async () => {
    const { app, config } = harness();
    const res = await request(app).get("/api/health");
    expect(res.status).toBe(200);
    expect(res.body.status).toBe("ok");
    expect(config.host).toBe("127.0.0.1");
    expect(res.body.tables).toEqual(
      expect.arrayContaining(["runs", "jobs", "uploads", "corrections_log"]),
    );
    expect(res.body.pipelineFound).toBe(true);
  });

  it("allows only the configured web origin", async () => {
    const { app } = harness(undefined, { WEB_ORIGIN: "http://127.0.0.1:3000" });
    const allowed = await request(app).get("/api/health").set("Origin", "http://127.0.0.1:3000");
    expect(allowed.headers["access-control-allow-origin"]).toBe("http://127.0.0.1:3000");
    const other = await request(app).get("/api/health").set("Origin", "http://evil.example");
    expect(other.headers["access-control-allow-origin"]).toBeUndefined();
  });

  it("returns JSON for unknown API paths", async () => {
    const { app } = harness();
    const res = await request(app).get("/api/nope");
    expect(res.status).toBe(404);
    expect(res.body).toEqual({ error: "not_found" });
  });

  it("rejects a bad port", () => {
    expect(() => loadConfig({ API_PORT: "banana" })).toThrow(/API_PORT/);
  });
});
