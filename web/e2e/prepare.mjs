// Copies the committed fixture into a fresh, throwaway repository root for each e2e run.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const tmp = path.join(here, ".tmp");
fs.rmSync(tmp, { recursive: true, force: true });
fs.cpSync(path.join(here, "fixture"), path.join(tmp, "fixture"), { recursive: true });
fs.mkdirSync(path.join(tmp, "data"), { recursive: true });
console.log(`e2e fixture ready in ${tmp}`);
