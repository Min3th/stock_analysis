import { createApp } from "./app.js";
import { loadConfig } from "./config.js";
import { openDb } from "./db.js";

const config = loadConfig();
const db = openDb(config.dbPath);
const app = createApp(config, db);

// Bound to the loopback interface only: this is a single-user local tool.
const server = app.listen(config.port, config.host, () => {
  console.log(`CSE screening API listening on http://${config.host}:${config.port}`);
});

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.on(signal, () => {
    server.close(() => {
      db.close();
      process.exit(0);
    });
  });
}
