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

## Notes

- Node 20 or later. `better-sqlite3` is a native module; the install downloads a
  prebuilt binary for your Node version.
- SQLite lives in `web/data/` (git-ignored). Run output stays in `data/runs/<run_id>/`.
- Every page carries the same neutral disclaimer; no page ranks or scores companies.
