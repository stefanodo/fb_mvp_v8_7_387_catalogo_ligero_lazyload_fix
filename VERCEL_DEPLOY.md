# Vercel Deployment Guide

This document describes how to connect this repository to Vercel and deploy the FastAPI app (backend) as a serverless function.

Overview
- The project exposes a Vercel serverless entrypoint at `api/index.py` which imports the ASGI `app` from `backend/app/main.py`.
- `vercel.json` is configured to use `@vercel/python` and already includes a `buildCommand: "cd backend && python migrate.py"`.

Prerequisites
- A Vercel account and access to the Git provider where this repo lives (GitHub/GitLab).
- A PostgreSQL instance for production (Vercel Postgres recommended) and its connection string.
- Secrets you must set on Vercel: `DATABASE_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` (optional), `RECIPE_AI_ALLOW_COMMIT` (0/1), any other production secrets used by your deployment.

Quick steps (Dashboard)
1. Sign in to Vercel and click "New Project" → Import Project → select the repository.
2. In the import screen:
   - Framework Preset: "Other" (or leave default).
   - Root Directory: leave blank (project root).
   - Build Command: leave as-is (the repo already has `vercel.json` which sets `cd backend && python migrate.py`).
   - Output Directory: leave empty.
3. Under "Environment Variables" add the required variables for Production:
   - `DATABASE_URL` = `postgresql://user:pass@host:port/dbname`
   - `OPENAI_API_KEY` (optional)
   - `ANTHROPIC_API_KEY` (optional)
   - `RECIPE_AI_ALLOW_COMMIT` = `0` (default; `1` enables auto-commit of IA drafts)
   - Any other secrets your deployment needs
4. Finish import and trigger a Deploy. The build will install dependencies (from `requirements.txt`) and run `cd backend && python migrate.py` during the build if `DATABASE_URL` is set. If `DATABASE_URL` is not set, the migration will skip safely.

Quick steps (Vercel CLI)
1. Install CLI:
```bash
npm i -g vercel
# or
npx vercel login
```
2. From repo root, link or deploy:
```bash
vercel login
vercel link # link to an existing project or create a new one interactively
# Add production env vars:
vercel env add DATABASE_URL production
vercel env add OPENAI_API_KEY production
# Deploy to production:
vercel --prod
```
Note: `vercel env add` will prompt for values; you can also set `VERCEL_TOKEN` and run non-interactively.

Checks after deploy
- Visit the public URL provided by Vercel. The app routes are served by the serverless function at `api/index.py` which exposes the FastAPI `app`.
- Check Vercel's deployment logs if the build fails (common failures: missing env vars, dependency wheels failing to build).
- If the migration runs during build and your Postgres is reachable, verify tables exist.

Troubleshooting notes
- If your build fails on `psycopg2-binary` wheel compilation, try using `psycopg` (psycopg3) instead — `requirements.txt` already supports `psycopg2-binary` but the code falls back to `psycopg` if present.
- If static assets are large, consider serving them via Vercel's static hosting rather than through the serverless function.
- If you prefer the app to run on a persistent container (not serverless), consider using another host (DigitalOcean App Platform, Render, or a container on Cloud Run/AKS). Vercel's Python functions are serverless and should work for this app, but they have cold-start characteristics.

Files we adjusted to improve Vercel compatibility
- `api/index.py` — fixed `sys.path` resolution to import `backend/app/main.py` reliably.
- `backend/migrate.py` — fixed `sys.path` resolution for consistent behavior during build/run.

If you want, I can:
- Prepare a `vercel-deploy.sh` script that uses the Vercel CLI (interactive tokens excluded),
- Create a list of exact environment variables required by the code (I can scan the repo for `os.getenv` usages),
- Or (if you provide Vercel credentials/VERCEL_TOKEN and confirm) run the Vercel CLI commands to create the project and set env vars for you.

Next step — pick one:
- I can create `vercel-deploy.sh` and a short env-vars manifest now.
- Or I can generate exact ENV list by scanning the codebase for `os.getenv` usages and config keys.

Which would you prefer?