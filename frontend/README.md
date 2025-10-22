# Airbnb Listing Assessor — Frontend

HostScore's web client renders Airbnb assessments produced by the FastAPI backend. It queues a render in Playwright, runs heuristic scoring, and visualises the highest-impact fixes for photos, copy, amenities, and trust signals.

## Prerequisites

- Node.js 20+
- Backend API reachable at `http://localhost:8000` (or any `PUBLIC_API_BASE`)

## Setup

```bash
cd frontend
npm install
```

Create `.env.local` (optional) to point at a remote backend (values shown are defaults):

```bash
PUBLIC_API_BASE=
BACKEND_API_BASE=http://127.0.0.1:8000
```

If omitted, requests fall back to relative `/assess`, which works when the backend and frontend share an origin during local development or behind a proxy.

## Development

```bash
npm run dev -- --open
```

This runs SvelteKit with hot-module reloading on <http://localhost:5173>. The frontend automatically reruns an assessment when you navigate to `/?url=https://www.airbnb.com/rooms/...`.

## Quality checks

```bash
npm run check
```

This synchronises generated types and runs `svelte-check` for static analysis.

## Feature highlights

- URL form with optional "force fresh render" toggle to bypass cached results.
- Live loading indicator while the backend renders the Airbnb listing in Playwright.
- Score dashboard summarising overall conversion readiness and section breakdowns.
- Detail cards for photo coverage, listing copy heuristics, and amenities evidence.
- Ordered list of top fixes with impact badges and actionable remediation steps.
