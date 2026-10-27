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

## Notes

- Node 20 or later. `better-sqlite3` is a native module; the install downloads a
  prebuilt binary for your Node version.
- SQLite lives in `web/data/` (git-ignored). Run output stays in `data/runs/<run_id>/`.
- Every page carries the same neutral disclaimer; no page ranks or scores companies.
