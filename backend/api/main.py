"""FastAPI entrypoint for the Airbnb listing assessor backend."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from httpx import AsyncClient
from playwright.async_api import Error as PlaywrightError

from .browser import BrowserManager
from .cache import AssessmentCache
from .extract import render_listing
from .heuristics import run_heuristics
from .models import AssessmentRequest, AssessmentResponse
from .scorer import LLMSettings, refine_assessment
from .utils import build_cache_key, normalize_listing_url

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Airbnb Listing Assessor",
    version="0.1.0",
    description="Evaluate Airbnb listings for conversion-readiness heuristics.",
)

_cors_origins = [
    origin.strip()
    for origin in os.getenv("API_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
if not _cors_origins:
    _cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_startup_lock = asyncio.Lock()
_is_ready = False

_browser_manager: Optional[BrowserManager] = None
_response_cache: Optional[AssessmentCache[str, AssessmentResponse]] = None
_llm_settings: Optional[LLMSettings] = None
_llm_client: Optional[AsyncClient] = None


@app.on_event("startup")
async def on_startup() -> None:
    """Initialize global resources (Playwright, cache, HTTP clients)."""
    global _is_ready, _browser_manager, _response_cache, _llm_settings, _llm_client

    async with _startup_lock:
        if _is_ready:
            return

        max_concurrency = int(os.getenv("MAX_CONCURRENCY", "4"))
        ttl_seconds = int(os.getenv("CACHE_TTL_SECONDS", "900"))
        cache_maxsize = int(os.getenv("CACHE_MAXSIZE", "128"))
        headless = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() != "false"
        disable_sandbox = os.getenv("PLAYWRIGHT_DISABLE_SANDBOX", "true").lower() != "false"

        _browser_manager = BrowserManager(
            headless=headless,
            max_concurrency=max_concurrency,
            disable_sandbox=disable_sandbox,
        )
        _response_cache = AssessmentCache[str, AssessmentResponse](
            maxsize=cache_maxsize,
            ttl_seconds=ttl_seconds,
        )

        api_key = os.getenv("HAIKU_API_KEY")
        if api_key:
            _llm_settings = LLMSettings(
                api_key=api_key,
                model=os.getenv("HAIKU_MODEL", "claude-haiku-4-5"),
                timeout_seconds=int(os.getenv("HAIKU_TIMEOUT_SECONDS", "10")),
                max_output_tokens=int(os.getenv("HAIKU_MAX_OUTPUT_TOKENS", "512")),
            )
            _llm_client = AsyncClient(timeout=_llm_settings.timeout_seconds)
            logger.info("LLM integration enabled.")
        else:
            logger.info("LLM integration disabled (no HAIKU_API_KEY provided).")

        _is_ready = True
        logger.info("Backend startup complete.")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Dispose of global resources."""
    global _is_ready, _browser_manager, _llm_client

    _is_ready = False

    if _browser_manager:
        await _browser_manager.close()
        _browser_manager = None

    if _llm_client:
        await _llm_client.aclose()
        _llm_client = None

    logger.info("Backend shutdown complete.")


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    """Simple readiness probe for deployment targets."""
    return {"status": "ok" if _is_ready else "initializing"}


@app.post("/assess", response_model=AssessmentResponse)
async def assess_listing(payload: AssessmentRequest) -> AssessmentResponse:
    """Assess an Airbnb listing and return structured feedback."""
    if not _is_ready or _browser_manager is None or _response_cache is None:
        raise HTTPException(status_code=503, detail="Service initializing, try again.")

    try:
        normalized_url = normalize_listing_url(str(payload.url))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    cache_key = build_cache_key(normalized_url)
    if not payload.force:
        cached = _response_cache.get(cache_key)
        if cached:
            logger.debug("Cache hit for %s", normalized_url)
            return cached

    logger.info("Assessing listing %s", normalized_url)
    try:
        content = await render_listing(normalized_url, _browser_manager)
    except PlaywrightError as exc:
        logger.exception("Playwright failed to render %s", normalized_url)
        raise HTTPException(status_code=502, detail="Failed to render Airbnb listing.") from exc
    except Exception as exc:  # pragma: no cover - catch-all for resiliency
        logger.exception("Unexpected error rendering %s", normalized_url)
        raise HTTPException(status_code=500, detail="Unexpected error rendering listing.") from exc

    heuristics = run_heuristics(content)
    response = AssessmentResponse(
        overall=heuristics.overall,
        section_scores=heuristics.section_scores,
        photo_stats=heuristics.photo_stats,
        copy_stats=heuristics.copy_stats,
        amenities=heuristics.amenities,
        trust_signals=heuristics.trust_stats,
        top_fixes=heuristics.recommendations,
    )

    context_payload = {
        "summary": content.summary,
        "description": content.description,
        "house_rules": content.house_rules,
        "reviews": content.reviews,
        "amenities_listed": content.amenities_listed,
    }

    refined = await refine_assessment(
        response,
        _llm_settings,
        _llm_client,
        context=context_payload,
    )

    _response_cache.set(cache_key, refined)
    return refined
