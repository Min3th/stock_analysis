import path from "node:path";
import { defineConfig } from "@playwright/test";

const tmp = path.resolve(__dirname, "e2e", ".tmp");
const API = "http://127.0.0.1:4100";
const APP = "http://127.0.0.1:3100";

/**
 * The tests run the real API and the production-built Next.js app against a throwaway repository root that holds
 * a stub `main.py` and a committed fixture run (e2e/fixture). No network, no real pipeline.
 */
export default defineConfig({
  testDir: "e2e",
  outputDir: "e2e/.results",
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: { baseURL: APP, acceptDownloads: true, trace: "retain-on-failure" },
  webServer: [
    {
      command: "node e2e/prepare.mjs && npx tsx api/src/server.ts",
      url: `${API}/api/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        API_PORT: "4100",
        REPO_ROOT: path.join(tmp, "fixture", "repo"),
        WEB_DATA_DIR: path.join(tmp, "data"),
        WEB_ORIGIN: APP,
        WEB_URL: APP,
        PYTHON_BIN: process.env.PYTHON_BIN ?? "python",
      },
    },
    {
      // A production build: no on-demand compiles or hot reloads to disturb a click.
      command: "npx next build app && npx next start app --hostname 127.0.0.1 --port 3100",
      url: APP,
      reuseExistingServer: false,
      timeout: 300_000,
      env: { API_URL: API, NEXT_DIST_DIR: ".next-e2e" },
    },
  ],
});
