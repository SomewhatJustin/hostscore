# Railway Deployment Guide

This project ships two deployable units:

- FastAPI + Playwright backend (`backend/`)
- SvelteKit frontend (`frontend/`)

Railway can run both from the GitHub repository as separate services. The sections below assume you have already imported the repo into Railway.

## Backend (FastAPI)

1. **Create a new service** in Railway and choose the GitHub repo.
2. When prompted for build configuration, switch to **Dockerfile** mode and set:
   - Dockerfile path: `backend/Dockerfile`
   - Build context: `backend`
3. Railway automatically sets the `PORT` environment variable. The Docker image now reads it (`${PORT:-8000}`) so no extra work is necessary.
4. Add environment variables as needed:
   - `API_ALLOWED_ORIGINS` (comma separated) — set to your frontend origin to lock CORS.
   - `HAIKU_API_KEY` plus optional `HAIKU_*` overrides if you want LLM refinement.
   - Tuning knobs: `CACHE_TTL_SECONDS`, `CACHE_MAXSIZE`, `MAX_CONCURRENCY`.
   - Leave `PLAYWRIGHT_DISABLE_SANDBOX` at the default (`true`) unless the target runtime supports Chromium's sandbox.
5. Configure the **Health Check** path to `/healthz` so Railway only routes traffic when Playwright is warmed up.

## Frontend (SvelteKit)

1. Add a second Railway service pointing at the same repo.
2. Use the Nixpacks builder (default). The repo-level `npm run build`/`npm run start` scripts already delegate into `frontend/`, so Railway will pick them up automatically. If you prefer to override manually, mirror these commands:
   - Build: `npm run build`
   - Start: `npm run start`
3. Set the following variables on the frontend service:
   - `PUBLIC_API_BASE` — leave blank to proxy to the backend when both are on the same domain, or set to the backend's public URL.
   - `BACKEND_API_BASE` — point at the backend service's internal HTTPS endpoint if you plan to call it directly.
4. The Vite preview server trusts all forwarded hosts (`preview.allowedHosts: true`), so you can use the default Railway domain out of the box.
5. Optionally enable a deploy hook so the frontend redeploys after the backend completes to pick up schema changes.

## Verification Checklist

- [ ] Backend service boots and `/healthz` returns `{"status":"ok"}`.
- [ ] Playwright launches (panel will show Chromium download if Railway purges cache).
- [ ] Frontend loads in preview, can submit a listing, and receives JSON from the backend.
- [ ] Railway domain(s) added to `API_ALLOWED_ORIGINS`.
- [ ] Haiku credentials stored as Railway environment variables (if LLM refinement is required).
