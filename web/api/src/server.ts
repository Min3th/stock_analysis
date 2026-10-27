import { createApp } from "./app.js";
import { loadConfig } from "./config.js";
import { openDb } from "./db.js";
import { JobQueue } from "./jobs.js";
import { playwrightRenderer } from "./pdf.js";

const config = loadConfig();
const db = openDb(config.dbPath);
const queue = new JobQueue(config, db);
const pdf = playwrightRenderer(config.webUrl);
const app = createApp(config, db, queue, { pdf });

// Bound to the loopback interface only: this is a single-user local tool.
const server = app.listen(config.port, config.host, () => {
  console.log(`CSE screening API listening on http://${config.host}:${config.port}`);
});

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.on(signal, () => {
    server.close(() => {
      void pdf.close();
      db.close();
      process.exit(0);
    });
  });
}
