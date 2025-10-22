# Repository Guidelines

## Project Structure & Module Organization
- `backend/api` contains the FastAPI service: `main.py` exposes routes, `browser.py` handles Playwright orchestration, `heuristics.py` scores listings, and `cache.py` keeps recent responses warm.
- `backend/scripts/assess.py` is a lightweight CLI wrapper; mirror new operational scripts here and import from `backend/api` packages to avoid drift.
- Shared runtime dependencies and Docker build context live in `backend/requirements.txt` and `backend/Dockerfile`.
- `frontend/` holds the SvelteKit client described in `frontend/README.md`; add components under `frontend/src` as the UI solidifies.
- Keep architectural notes current in `MASTERPLAN.md`; link to relevant sections when opening cross-cutting work.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate && pip install -r backend/requirements.txt`: create an isolated backend environment.
- `playwright install chromium`: install the browser runtime required for `render_listing`.
- `uvicorn backend.api.main:app --reload --port 8080`: serve the API locally with live reload.
- `python backend/scripts/assess.py https://www.airbnb.com/rooms/...`: run assessments from the CLI for quick smoke checks.
- `cd frontend && npm install && npm run dev -- --open`: bootstrap and iterate on the SvelteKit app once UI work begins.

## Coding Style & Naming Conventions
- Python code follows PEP 8 with four-space indents, type-hinted signatures, and descriptive async function names (e.g., `normalize_listing_url`).
- Group functionality by concern: browser orchestration in `browser.py`, heuristics in `heuristics.py`, response shaping in `models.py`.
- Prefer dataclasses or Pydantic models for structured payloads; avoid ad-hoc dicts.
- Svelte files should use PascalCase component filenames, colocate stores/utilities in `frontend/src/lib`, and keep Tailwind classes consistent when introduced.

## Testing Guidelines
- Place backend unit tests under `backend/tests/`, mirroring module structure (`test_browser.py`, `test_cache.py`, etc.), and run them with `pytest`.
- Use `pytest-asyncio` for coroutine tests and cache heavy Playwright interactions behind fixtures or fakes.
- Target ≥80% coverage on heuristics, caching, and normalization logic via `pytest --maxfail=1 --disable-warnings --cov=backend/api`.
- Record sample Airbnb pages for deterministic heuristic tests; store sanitized fixtures in `backend/tests/fixtures`.

## Commit & Pull Request Guidelines
- Follow Conventional Commits (`feat:`, `fix:`, `refactor:`, `chore:`) so change logs remain machine-readable.
- Keep commits narrowly scoped and update `MASTERPLAN.md` alongside feature work.
- PRs should describe the problem, solution, and testing performed; attach `curl` outputs or screenshots when API/UI behavior changes.
- Document any new environment variables or migrations in the PR body and request review from domain owners before merging heuristic or scoring updates.

## Security & Configuration Tips
- Store secrets such as `HAIKU_API_KEY` outside the repo and load them via `.env` or your runtime provider.
- Respect the default headless Playwright settings; only disable sandboxing (`PLAYWRIGHT_DISABLE_SANDBOX=false`) when target infrastructure supports it.
- Sanitize logged listing data—avoid persisting raw URLs beyond cache keys, and guard future telemetry behind explicit opt-ins.

## MCP & Documentation Support
- You can use the Svelte MCP server for authoritative Svelte 5 and SvelteKit references; always start with the `list-sections` tool to surface relevant topics.
- After reviewing the `use_cases` metadata returned by `list-sections`, call `get-documentation` to pull every section needed for your task.
- Run `svelte-autofixer` on any Svelte snippet you author until it reports no issues; this keeps shared code aligned with best practices.
- When code lives only in the conversation, ask whether the user wants a Svelte Playground link before invoking `playground-link`, and skip the tool if the code was written to disk.
