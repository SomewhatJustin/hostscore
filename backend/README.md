# Airbnb Listing Assessor — Backend

FastAPI backend that renders Airbnb listings with Playwright, computes deterministic heuristics, and optionally refines results with the Haiku 4.5 LLM.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
playwright install chromium
```

## Environment

| Variable | Purpose | Default |
| --- | --- | --- |
| `HAIKU_API_KEY` | Enables LLM refinement of top fixes | _disabled_ |
| `HAIKU_MODEL` | Override Anthropic model id | `haiku-4.5` |
| `HAIKU_TIMEOUT_SECONDS` | LLM request timeout | `10` |
| `HAIKU_MAX_OUTPUT_TOKENS` | LLM output token cap | `512` |
| `CACHE_TTL_SECONDS` | Cache TTL for assessments | `900` |
| `CACHE_MAXSIZE` | Cache capacity | `128` |
| `MAX_CONCURRENCY` | Concurrent Playwright pages | `4` |
| `PLAYWRIGHT_HEADLESS` | Set to `false` to debug browser | `true` |
| `PLAYWRIGHT_DISABLE_SANDBOX` | Set to `false` if Chromium sandbox is available | `true` |
| `API_ALLOWED_ORIGINS` | Comma list of allowed CORS origins | `*` |

## Run locally

```bash
uvicorn api.main:app --reload --port 8080
```

Submit an assessment:

```bash
curl -X POST http://localhost:8080/assess \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.airbnb.com/rooms/123456"}'
```

## Docker

Build and run locally:

```bash
docker build -t airbnb-assessor-backend -f backend/Dockerfile backend
docker run --rm -p 8080:8080 -e HAIKU_API_KEY=... airbnb-assessor-backend
```
