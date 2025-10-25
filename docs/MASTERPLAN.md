Airbnb Listing Assessor — Masterplan (MVP)

    Scope guard: No DB, no auth, ship today. Python backend (FastAPI + Playwright) on Railway. Frontend is SvelteKit (deploy to Vercel or Railway). One LLM call (Haiku 4.5). Deterministic heuristics first; model refines and writes fixes. If you drift from this, that’s on you. 😈

0) Product Slice (what “done” means today)

    Input: Airbnb listing URL

    Output: JSON + UI with:

        Overall score (0–100)

        Section scores: photos, copy, amenities clarity, trust signals

        Top 5 Fixes (short, imperative, prioritized)

        Photo stats (count, median srcset width, near-duplicate ratio)

        Copy stats (word count, readability, structure flags)

        Amenity cross-audit (mentioned vs listed)

        Title suggestions (≤60 chars, no emoji/all-caps)

    Non-goals (today): comps, pricing intelligence, EXIF, image classifiers, auth, payments.

1) Architecture (ship-today)

    Frontend: SvelteKit (thin client → fetch to backend)

    Backend: FastAPI (Python 3.11), Playwright (Chromium)

    Deploy:

        Backend: Railway (one Docker image; autosleep/scale-to-zero)

        Frontend: Vercel or Railway (Vercel recommended for instant previews)

    State: None (no DB). In-memory LRU+TTL cache inside the backend process.

    LLM: Haiku 4.5 (single JSON response call). Strict schema, short context, 3s–5s budget.

2) Tech Choices (locked)
Backend

    fastapi, uvicorn[standard]

    playwright (Chromium)

    beautifulsoup4, trafilatura, readability-lxml

    textstat

    imagehash, Pillow (pHash + basic size; no EXIF)

    cachetools (LRU/TTL)

    httpx (timeouts/retries)

    pydantic, orjson, tenacity

Frontend

    SvelteKit, TypeScript, Tailwind, @tanstack/query (optional), zod for client validation.

Infra

    Railway for API (Docker)

    Vercel for SvelteKit (zero-config).
    Alt: host both on Railway to keep vendor count low.

3) Repository Layout

airbnb-assessor/
  backend/
    api/
      main.py            # FastAPI app + routes
      browser.py         # Playwright lifecycle (singleton)
      extract.py         # HTML → sections (title/summary/amenities/rules/reviews)
      heuristics.py      # photos/copy/amenities/trust deterministic checks
      scorer.py          # LLM call (Haiku 4.5) + schema validation
      cache.py           # LRU+TTL cache wrapper
      models.py          # Pydantic request/response schemas
      utils.py           # URL normalize, robots/UA, logging
    Dockerfile
    requirements.txt
    README.md
  frontend/
    (SvelteKit app)
  MASTERPLAN.md

4) API Contract
POST /assess

Request

{ "url": "https://www.airbnb.com/rooms/xxxx", "force": false }

Response (example)

{
  "overall": 82,
  "section_scores": {
    "photos": 78, "copy": 84, "amenities_clarity": 75, "trust_signals": 90
  },
  "photo_stats": {
    "count": 27,
    "median_srcset_px": 2048,
    "near_duplicate_ratio": 0.22,
    "coverage": ["bedroom","bath","kitchen","living","exterior_day"]
  },
  "copy_stats": {
    "word_count": 214,
    "flesch": 68.3,
    "second_person_pct": 1.4,
    "has_sections": true
  },
  "amenities": {
    "listed": ["wifi","parking","ac"],
    "text_hits": ["parking","desk"],
    "likely_present_not_listed": ["desk"],
    "listed_no_text_evidence": ["iron"]
  },
  "top_fixes": [
    { "impact":"high","reason":"photos missing exterior night",
      "how_to_fix":"Add 1 exterior night photo; show lit pathway and parking" }
  ],
  "title_suggestions": [
    "Modern Loft Near Downtown • Free Parking & Rooftop Deck"
  ],
  "notes": { "served_from_cache": true, "render_ms": 4880 }
}

GET /healthz

    Returns {"ok": true}

(Optional) POST /assess/html

    Accepts raw HTML if render fails (unblocks demos).

5) Heuristics (deterministic)
Photos

    Count: target ≥ 20

    Max width per image: parse from srcset (choose largest width token)

    Median width: target ≥ 1600 px

    Near-duplicates: pHash Hamming distance ≤ 8 considered near-duplicate; compute ratio

    Coverage (cheap): keyword heuristics in alt/filenames/section captions for bedroom|bath|kitchen|living|exterior

        Note: this is approximate; no EXIF, no classifiers today.

Copy (using your best practices)

    Lead with hooks: first 200 chars must include ≥2 of {location token, unique amenity, property type}

    Concise length: 120–300 words

    Readability: Flesch 60–80

    Tone: second-person density ≥1%; imperative verbs present; exclamations ≤2/200 words

    Keywords: city/neighborhood, property type, 1–3 anchor amenities in title/first paragraph

    Scannability: line breaks/short paragraphs; headings keywords {“The Space”, “Guest Access”, “Neighborhood”}

    Expectation-setting: presence of mild negatives/constraints (e.g., “steep stairs”, “road noise”) → honesty flag

Amenities cross-audit

    Build synonym map → canonical label.

    likely_present_not_listed = (description_hits ∪ photo_name_hits) − listed

    listed_no_text_evidence = listed − (description_hits ∪ photo_name_hits)

        Both are soft flags; do not penalize hard.

Trust signals

    House rules concise (≤ 12 bullets or short paragraph)

    Reviews mention cleanliness/location/host responsiveness (pull top 1–2 snippets if present)

    Price transparency: if a “fees”/“price per night” paragraph exists → small bonus

6) Scoring Rubric (weights)

photos:             0.35
copy:               0.35
amenities_clarity:  0.15
trust_signals:      0.15

    Each section = average of its checks (normalized 0–100), then multiply by weight.

    LLM can adjust ±10 within a section when it detects qualitative issues the heuristics miss (e.g., vague/overwrought copy).

7) LLM (Haiku 4.5) integration

Input (strict, compact):

    Heuristics JSON summary (<= 2KB)

    Title (<= 80 chars), first 250–300 words of description

    Airbnb amenity list (short)

    (Optional) 1–2 short review excerpts if easily extractable

System prompt (short):

    You are an Airbnb listing assessor. Follow the rubric. Output valid JSON only. Use short, imperative “how_to_fix”. No prose.

Output schema:

{
  "section_scores": {"photos":0,"copy":0,"amenities_clarity":0,"trust_signals":0},
  "top_fixes":[{"impact":"high|med|low","reason":"","how_to_fix":"","example":""}],
  "title_suggestions":["",""],
  "notes":[]
}

Guardrails

    Response validator (pydantic). If invalid or timeout → return heuristics-only with notice.

    Max tokens low; temperature ~0.3.

8) Caching (no DB)

    LRU+TTL inside process via cachetools.TTLCache(maxsize=200, ttl=900)

    Key: normalized URL + version hash of extractor (bump on code changes)

    Value: { html, sections, photo_meta, heuristics, llm_result, ts }

    Policy: if force=true skip cache; else return cached unless stale

    Stale-while-revalidate (cheap): if TTL expired but entry exists, serve cached with notes.stale=true and kick off async refresh (optional nice-to-have).

9) Failure modes & SLA

    Budget: < 25s P95 per request

    Timeouts: nav 12s; overall 20s; LLM 3–5s

    Graceful degradation: If render fails/429 → try lightweight HTML GET; else error with descriptive message and suggest /assess/html

    Backoffs: exponential on 429/503

10) Security & Ethics

    One fetch per request, custom UA, respect 429s

    No credentialed endpoints, no login

    Don’t store results (no DB); logs scrub URLs if you want

    Rate-limit by IP (simple token bucket in memory)

11) Dev & Deploy
Backend (Railway)

# Dev
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn api.main:app --reload --port 8000

# Docker
docker build -t airbnb-assessor .
# Run locally with Chromium sandbox disabled if needed:
docker run -p 8000:8000 --shm-size=1g --cap-add=SYS_ADMIN airbnb-assessor

# Railway
# 1) Create new service from repo
# 2) Set PORT=8000, PYTHONUNBUFFERED=1, PLAYWRIGHT_BROWSERS_PATH=0
# 3) Add LLM keys: HAIKU_API_KEY=...
# 4) Deploy; note public URL for frontend

Dockerfile

FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/api /app/api
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

Frontend (SvelteKit)

npm create svelte@latest frontend
cd frontend
npm i
npm i -D tailwindcss postcss autoprefixer
# configure Tailwind
npm run dev
# env
VITE_API_BASE=https://<railway-backend>/  # set per environment

UI spec (MVP)

    URL input → POST /assess

    Results grid: Overall score badge, 4 section meters, “Top 5 Fixes”

    Collapsible “Details” (photo/copy/amenity stats)

    Permalink with ?url=<encoded> and re-assess button

    Loading + error states

12) Milestones (today → next)

T-0 (2–4h)

    Scaffold backend modules + Playwright fetch + basic extraction

    Heuristics: photo count/median srcset, pHash dupes, copy stats, amenity presence via alias/fuzzy/embedding similarity

    Wire Haiku 4.5 call + schema validation

    LRU cache

    /assess works locally

T-1 (1–2h)

    SvelteKit page with URL form + fetch + render

    Simple styles, responsive

T-2 (30–60m)

    Dockerize backend, deploy to Railway

    Point frontend to prod API, deploy to Vercel

Bonus (tomorrow)

    Rate limit

    /assess/html

    Unit tests on 3–5 captured pages

    CLIP room coverage (later)

13) Tasks Checklist

Normalize URL & basic validation

Playwright render + networkidle + auto-scroll for lazy images

Extract: title, description, amenities, rules, first 2 review snippets (best-effort)

Photo meta: srcset parse → max width, pHash on thumbnails

Heuristics compute + weights

LLM prompt + client + pydantic response validation

LRU+TTL cache

API route + error handling

SvelteKit UI (form, result, states)

Deploy backend (Railway) + frontend (Vercel)

    README with env vars & usage

14) Env Vars

    HAIKU_API_KEY — LLM provider key

    API_BASE_URL — (optional) for CORS

    CACHE_TTL_SECONDS — default 900

    MAX_CONCURRENCY — Playwright pages (2–4)

15) “Don’t be cute” Rules

    Don’t use serverless browsers.

    Don’t fetch full images for all photos; use srcset widths; sample a few if you must.

    Don’t exceed 1 LLM call/request.

    Don’t add a DB (you said drop it). If you add one today, you’re stalling.

15a) Payments MVP (Partial Report Paywall)

    Generate one full assessment per listing request, but only return the “teaser” payload (overall score + single fix + minimal stats) to unauthenticated users. Return a `report_id` and cache the full JSON in the existing in-memory store.

    Add `POST /checkout` that creates a Stripe Checkout Session for a fixed $10 price. Encode `report_id` (and normalized URL) in session metadata; set success to `/report?report_id=…&session_id={CHECKOUT_SESSION_ID}` and cancel to the teaser view.

    Add `GET /assess/full` that accepts `report_id` and `session_id`, retrieves the Checkout Session, verifies `payment_status == "paid"` and matching metadata, then responds with the cached full report (regenerating if evicted). Return 402 if unpaid.

    Frontend: show the teaser report with an “Unlock full report” button → call `/checkout`, redirect to Stripe, then on return exchange `report_id` + `session_id` for the full dataset and hydrate the UI.

    Env: document `STRIPE_SECRET_KEY` (`STRIPE_PRICE_ID` optional) and Stripe test card workflow alongside deployment notes.

16) Future Backlog

    CLIP/VLM tags for room coverage + object detection (desk, hot tub, grill)

    Cross-listing support: Vrbo, Booking

    Basic comps crawler by neighborhood

    Stripe + rate-limits + saved reports

    Redis (when you horizontally scale)

Ship it. If you scope-creep, this won’t launch today.
