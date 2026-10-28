# CSE screening web app

A local, single-user app for the Python pipeline in the repository root.

- `api/` is an Express + TypeScript service. It binds to `127.0.0.1` only, keeps a
  small SQLite index (runs, jobs, uploads, submitted corrections) and reads the JSON
  that `main.py run --run-dir` writes. It never calculates a ratio.
- `app/` is a Next.js (App Router) UI. It proxies `/api` to the service, so the browser
  only talks to one origin.

All financial logic stays in Python. The web app displays, uploads and orchestrates.

## Setup

```powershell
cd web
copy .env.example .env      # adjust PYTHON_BIN if needed
npm install
npm run dev:api             # http://127.0.0.1:4000
npm run dev:app             # http://127.0.0.1:3000
```

`npm test` runs the API tests (Vitest + Supertest). `npm run typecheck` checks both
workspaces and `npm run build` builds them.

## Runs

`POST /api/runs {sector, period, ticker?, offline?}` queues a run. A single worker
executes `python main.py run ... --run-dir data/runs/<run_id>` one at a time, with an
argument array and no shell. The sector is checked against an allow-list (kept in step
with the Python package by a test), the ticker and period against strict patterns.
`GET /api/runs/:id/events` streams the process output as server-sent events (the stored
log is replayed first, so a late viewer sees everything). When the server restarts, any
run that was still queued or running is marked failed.

## Uploads

`POST /api/uploads` (multipart: `file`, `ticker`, `kind`, `periodEnd`, `periodMonths` for interims)
checks size and the `%PDF` header, stores the file under `web/data/uploads/pending/` by checksum
and runs `main.py extract` for the preview (nothing is stored in the pipeline yet). `POST
/api/uploads/:id/accept` calls `main.py uploads add`, which re-checks the universe and is the
only writer of `config/uploads.yml`; `DELETE /api/uploads/:id` discards it.

## Review and corrections

`GET /api/runs/:id/review` lists withheld and flagged values; the review page shows the cited PDF page
beside each item. `POST /api/corrections` validates the fields (metric name, plain number, unit and
scope allow-lists, page, reason) and calls `main.py corrections add` with `--flag=value` arguments, so
`config/corrections.yml` is only ever written by Python. A correction never edits a published run: the
original extraction stays on record and the next run of that company applies the correction, marking an
older one `superseded` when `supersedes` is given.

## PDF exports

`POST /api/exports {type: sector|company|review, runId, ticker?}` returns a PDF. The API opens the
app's print route (`/print/sector/<run>`, `/print/company/<run>/<ticker>`, `/print/review/<run>`) in
headless Chromium (Playwright), waits until the page reports its data loaded, and prints it to A4.
Each report starts with a cover (run id, scope, pipeline commit, config hash, finish time) and the
fixed disclaimer, and every page footer repeats it. The sector report is landscape and ends with a
sources appendix (URL and checksum per document); the company sheet lists each calculation with its
formula and input fact IDs, plus a citations table; the review pack lists every item with its source
text and page. A page that fails to load its data is never exported. The browser needs
`npx playwright install chromium` once.

## Tests

- `npm test` runs the API tests (Vitest and Supertest): validation, the job queue with a stub
  pipeline, SSE replay, tables, cited documents (including path-escape attempts), uploads,
  corrections and exports. No Python or browser is needed.
- `npm run e2e` runs Playwright against the real API and a production build of the app, using a
  throwaway repository root (`e2e/fixture`) with a stub `main.py` and a committed fixture run, so it
  needs no network and no cache. It covers the dashboard, an offline run, the sector table, the
  lineage drawer, the cited PDF, a correction, an upload preview and all three PDF exports. The first
  run needs `npx playwright install chromium`.
- The stub `main.py` only copies fixture JSON; the real pipeline is covered by the Python tests.

## Notes

- `WEB_URL` (default `http://127.0.0.1:3000`) is where the API finds the print routes.
- Node 20 or later. `better-sqlite3` is a native module; the install downloads a
  prebuilt binary for your Node version.
- SQLite lives in `web/data/` (git-ignored). Run output stays in `data/runs/<run_id>/`.
- Every page carries the same neutral disclaimer; no page ranks or scores companies.
