import { spawn } from "node:child_process";
import type { Config } from "./config.js";

export interface PythonResult {
  code: number | null;
  stdout: string;
  stderr: string;
}

/** Runs `python main.py <args>` and collects its output. Injected in tests. */
export type PythonRunner = (args: string[]) => Promise<PythonResult>;

/** Argument array, no shell, hard timeout: the arguments are validated by the callers. */
export function pythonRunner(config: Config, timeoutMs = 5 * 60_000): PythonRunner {
  return (args) =>
    new Promise((resolve) => {
      let stdout = "";
      let stderr = "";
      let settled = false;
      const done = (result: PythonResult) => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          resolve(result);
        }
      };
      const child = spawn(config.pythonBin, ["main.py", ...args], {
        cwd: config.repoRoot,
        shell: false,
        windowsHide: true,
        env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" },
      });
      const timer = setTimeout(() => {
        child.kill();
        done({ code: null, stdout, stderr: `${stderr}\nTimed out after ${timeoutMs / 1000}s` });
      }, timeoutMs);
      child.stdout.setEncoding("utf-8").on("data", (chunk: string) => (stdout += chunk));
      child.stderr.setEncoding("utf-8").on("data", (chunk: string) => (stderr += chunk));
      child.on("error", (error) => done({ code: null, stdout, stderr: error.message }));
      child.on("close", (code) => done({ code, stdout, stderr }));
    });
}
